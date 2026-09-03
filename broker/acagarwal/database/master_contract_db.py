"""AC Agarwal Symphony XTS Master Contract Database."""

import csv
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
from sqlalchemy import Column, Float, Index, Integer, Sequence, String
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import scoped_session, sessionmaker

from broker.acagarwal.baseurl import MARKET_DATA_URL
from database.auth_db import get_auth_token
from database.engine_factory import create_db_engine
from extensions import socketio
from utils.httpx_client import get_httpx_client
from utils.logging import get_logger

logger = get_logger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_db_engine(DATABASE_URL)
db_session = scoped_session(sessionmaker(autocommit=False, autoflush=False, bind=engine))
Base = declarative_base()
Base.query = db_session.query_property()


class SymToken(Base):
    __tablename__ = "symtoken"
    id = Column(Integer, Sequence("symtoken_id_seq"), primary_key=True)
    symbol = Column(String, nullable=False, index=True)
    brsymbol = Column(String, nullable=False, index=True)
    name = Column(String)
    exchange = Column(String, index=True)
    brexchange = Column(String, index=True)
    token = Column(String, index=True)
    expiry = Column(String)
    strike = Column(Float)
    lotsize = Column(Integer)
    instrumenttype = Column(String)
    tick_size = Column(Float)

    __table_args__ = (Index("idx_symbol_exchange", "symbol", "exchange"),)


def init_db():
    logger.info("Initializing AC Agarwal Master Contract DB")
    Base.metadata.create_all(bind=engine)


def delete_symtoken_table():
    logger.info("Deleting Symtoken Table")
    SymToken.query.delete()
    db_session.commit()


def copy_from_dataframe(df):
    logger.info("Performing Bulk Insert into SymToken")
    data_dict = df.to_dict(orient="records")
    existing_tokens = {result.token for result in db_session.query(SymToken.token).all()}
    filtered_data_dict = [row for row in data_dict if str(row["token"]) not in existing_tokens]

    try:
        if filtered_data_dict:
            db_session.bulk_insert_mappings(SymToken, filtered_data_dict)
            db_session.commit()
            logger.info(f"Bulk insert completed with {len(filtered_data_dict)} records.")
    except Exception as e:
        logger.error(f"Error during bulk insert: {e}")
        db_session.rollback()


def download_csv_acagarwal_data(output_path):
    logger.info("Downloading AC Agarwal Master Contract CSV Files")
    exchange_segments = ["NSECM", "NSEFO", "NSECD", "BSECM", "BSEFO", "MCXFO"]
    headers_equity = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low,FreezeQty,TickSize,LotSize,Multiplier,DisplayName,ISIN,PriceNumerator,PriceDenominator,DetailedDescription,ExtendedSurvIndicator,CautionIndicator,GSMIndicator\n"
    headers_fo = "ExchangeSegment,ExchangeInstrumentID,InstrumentType,Name,Description,Series,NameWithSeries,InstrumentID,PriceBand.High,PriceBand.Low,FreezeQty,TickSize,LotSize,Multiplier,UnderlyingInstrumentId,UnderlyingIndexName,ContractExpiration,StrikePrice,OptionType,DisplayName,PriceNumerator,PriceDenominator,DetailedDescription\n"

    client = get_httpx_client()
    headers = {"Content-Type": "application/json"}
    os.makedirs(output_path, exist_ok=True)

    for segment in exchange_segments:
        try:
            payload = json.dumps({"exchangeSegmentList": [segment]})
            response = client.post(
                f"{MARKET_DATA_URL}/instruments/master", headers=headers, content=payload, timeout=30
            )
            if response.status_code != 200:
                logger.warning(f"Failed to download {segment} (status {response.status_code})")
                continue

            data = response.json()
            if "result" not in data or not data["result"]:
                logger.warning(f"Empty result for {segment}")
                continue

            header = headers_equity if segment in ["NSECM", "BSECM"] else headers_fo
            segment_output_path = f"{output_path}/{segment}.csv"

            csv_data = data["result"].strip().split("\n")
            csv_data = [row.split("|") for row in csv_data if row.strip()]

            with open(segment_output_path, "w", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header.strip().split(","))
                writer.writerows(csv_data)
            logger.info(f"Downloaded and saved {segment_output_path}")
        except Exception as e:
            logger.error(f"Error downloading {segment}: {e}")


def fetch_index_list():
    logger.info("Fetching Index List")
    exchange_segments = [1, 11]  # 1 = NSE, 11 = BSE
    headers = {"Content-Type": "application/json"}
    client = get_httpx_client()
    index_data = []

    for segment in exchange_segments:
        try:
            url = f"{MARKET_DATA_URL}/instruments/indexlist?exchangeSegment={segment}"
            response = client.get(url, headers=headers, timeout=15)
            if response.status_code != 200:
                continue

            data = response.json()
            if "result" not in data or "indexList" not in data["result"]:
                continue

            for index_entry in data["result"]["indexList"]:
                if "_" in index_entry:
                    symbol_name, token = index_entry.rsplit("_", 1)
                    index_data.append({
                        "brsymbol": index_entry,
                        "symbol": symbol_name,
                        "exchange": "NSE_INDEX" if segment == 1 else "BSE_INDEX",
                        "token": token,
                    })
        except Exception as e:
            logger.error(f"Error fetching index list for segment {segment}: {e}")

    return index_data


BSE_INDEX_SYMBOL_MAP = {
    "SNSX50": "SENSEX50",
    "SNXT50": "BSESENSEXNEXT50",
    "MID150": "BSE150MIDCAPINDEX",
    "LMI250": "BSE250LARGEMIDCAPINDEX",
    "MSL400": "BSE400MIDSMALLCAPINDEX",
    "AUTO": "BSEAUTO",
    "BSE CG": "BSECAPITALGOODS",
    "CARBON": "BSECARBONEX",
    "BSE CD": "BSECONSUMERDURABLES",
    "CPSE": "BSECPSE",
    "DOL100": "BSEDOLLEX100",
    "DOL200": "BSEDOLLEX200",
    "DOL30": "BSEDOLLEX30",
    "ENERGY": "BSEENERGY",
    "BSEFMC": "BSEFASTMOVINGCONSUMERGOODS",
    "FIN": "BSEFINANCIALSERVICES",
    "FINSER": "BSEFINANCIALSERVICES",
    "GREENX": "BSEGREENEX",
    "BSE HC": "BSEHEALTHCARE",
    "INFRA": "BSEINDIAINFRASTRUCTUREINDEX",
    "INDSTR": "BSEINDUSTRIALS",
    "BSE IT": "BSEINFORMATIONTECHNOLOGY",
    "LRGCAP": "BSELARGECAP",
    "METAL": "BSEMETAL",
    "MIDCAP": "BSEMIDCAP",
    "MIDSEL": "BSEMIDCAPSELECTINDEX",
    "OILGAS": "BSEOIL&GAS",
    "POWER": "BSEPOWER",
    "BSEPBI": "BSEPSU",
    "REALTY": "BSEREALTY",
    "SMLCAP": "BSESMALLCAP",
    "SMLSEL": "BSESMALLCAPSELECTINDEX",
    "SMEIPO": "BSESMEIPO",
    "TECK": "BSETECK",
    "TELCOM": "BSETELECOM",
}


def normalize_bse_index_symbols(symbol_series: pd.Series) -> pd.Series:
    normalized = symbol_series.astype(str).str.upper().str.strip()
    normalized = normalized.str.replace(r"\s+", " ", regex=True)
    normalized = normalized.replace(BSE_INDEX_SYMBOL_MAP)
    return normalized.str.replace(r"[\s\-]+", "", regex=True)


def process_acagarwal_nse_csv(path):
    file_path = f"{path}/NSECM.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["Series"].isin(["EQ", "BE", "SM"])]

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"].astype(str) + "-EQ"
    token_df["brsymbol"] = df["DisplayName"].fillna(df["Name"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "NSE"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = ""
    token_df["strike"] = 0.0
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = "EQ"
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)
    return token_df


def process_acagarwal_bse_csv(path):
    file_path = f"{path}/BSECM.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["Series"].isin(["A", "B", "T", "X"])]

    token_df = pd.DataFrame()
    token_df["symbol"] = df["Name"]
    token_df["brsymbol"] = df["DisplayName"].fillna(df["Name"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "BSE"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = ""
    token_df["strike"] = 0.0
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = "EQ"
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)
    return token_df


def process_acagarwal_nfo_csv(path):
    file_path = f"{path}/NSEFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["ContractExpiration"] != "1"]
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])
    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(0.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    token_df = pd.DataFrame()
    token_df["symbol"] = df["symbol"]
    token_df["brsymbol"] = df["Description"].fillna(df["symbol"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "NFO"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"]
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"}).fillna("FUT")
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)
    return token_df


def process_acagarwal_cds_csv(path):
    file_path = f"{path}/NSECD.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["ContractExpiration"] != "1"]
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])
    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(0.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(float(row['StrikePrice']))) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    token_df = pd.DataFrame()
    token_df["symbol"] = df["symbol"]
    token_df["brsymbol"] = df["Description"].fillna(df["symbol"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "CDS"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"]
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"}).fillna("FUT")
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.0025).astype(float)
    return token_df


def process_acagarwal_bfo_csv(path):
    file_path = f"{path}/BSEFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["ContractExpiration"] != "1"]
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])
    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(0.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    token_df = pd.DataFrame()
    token_df["symbol"] = df["symbol"]
    token_df["brsymbol"] = df["Description"].fillna(df["symbol"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "BFO"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"]
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"}).fillna("FUT")
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)
    return token_df


def process_acagarwal_mcx_csv(path):
    file_path = f"{path}/MCXFO.csv"
    if not os.path.exists(file_path):
        return pd.DataFrame()

    df = pd.read_csv(file_path)
    df = df[df["ContractExpiration"] != "1"]
    df["ContractExpiration"] = pd.to_datetime(df["ContractExpiration"])
    df["StrikePrice"] = pd.to_numeric(df["StrikePrice"], errors="coerce").fillna(0.0)

    df["symbol"] = df.apply(
        lambda row: f"{row['Name']}"
        f"{row['ContractExpiration'].strftime('%d%b%y').upper()}"
        f"{'' if row['OptionType'] == 1 else (str(int(float(row['StrikePrice']))) if float(row['StrikePrice']) == int(float(row['StrikePrice'])) else str(row['StrikePrice'])) if pd.notna(row['StrikePrice']) else ''}"
        f"{'FUT' if row['OptionType'] == 1 else 'CE' if row['OptionType'] == 3 else 'PE'}",
        axis=1,
    )

    token_df = pd.DataFrame()
    token_df["symbol"] = df["symbol"]
    token_df["brsymbol"] = df["Description"].fillna(df["symbol"])
    token_df["name"] = df["Name"]
    token_df["exchange"] = "MCX"
    token_df["brexchange"] = df["ExchangeSegment"]
    token_df["token"] = df["ExchangeInstrumentID"].astype(str)
    token_df["expiry"] = df["ContractExpiration"].dt.strftime("%d-%b-%y").str.upper()
    token_df["strike"] = df["StrikePrice"]
    token_df["lotsize"] = pd.to_numeric(df["LotSize"], errors="coerce").fillna(1).astype(int)
    token_df["instrumenttype"] = df["OptionType"].map({1: "FUT", 3: "CE", 4: "PE"}).fillna("FUT")
    token_df["tick_size"] = pd.to_numeric(df["TickSize"], errors="coerce").fillna(0.05).astype(float)
    return token_df


def process_index_data(index_data):
    df = pd.DataFrame(index_data)
    if df.empty:
        return df

    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["symbol"] = df["symbol"].str.replace(r"\s+", " ", regex=True)

    nse_index_map = {
        "NIFTY 50": "NIFTY",
        "NIFTY BANK": "BANKNIFTY",
        "INDIA VIX": "INDIAVIX",
        "NIFTY FIN SERVICE": "FINNIFTY",
        "NIFTY MID SELECT": "MIDCPNIFTY",
        "NIFTY NEXT 50": "NIFTYNXT50",
    }
    df["symbol"] = df["symbol"].replace(nse_index_map)

    bse_idx_mask = df["exchange"] == "BSE_INDEX"
    df.loc[bse_idx_mask, "symbol"] = normalize_bse_index_symbols(df.loc[bse_idx_mask, "symbol"])
    df["symbol"] = df["symbol"].str.replace(r"[\s\-]+", "", regex=True)

    df["name"] = df["symbol"]
    df["brexchange"] = df["exchange"]
    df["expiry"] = ""
    df["strike"] = 1.0
    df["lotsize"] = 1
    df["instrumenttype"] = "INDEX"
    df["tick_size"] = 0.05
    return df


def delete_acagarwal_temp_data(output_path):
    if os.path.exists(output_path):
        for filename in os.listdir(output_path):
            file_path = os.path.join(output_path, filename)
            if filename.endswith(".csv") and os.path.isfile(file_path):
                os.remove(file_path)


def master_contract_download():
    logger.info("Downloading Master Contract for AC Agarwal")
    output_path = "tmp"

    try:
        download_csv_acagarwal_data(output_path)
        delete_symtoken_table()

        for proc_func, seg_name in [
            (process_acagarwal_nse_csv, "NSE"),
            (process_acagarwal_bse_csv, "BSE"),
            (process_acagarwal_nfo_csv, "NFO"),
            (process_acagarwal_cds_csv, "CDS"),
            (process_acagarwal_bfo_csv, "BFO"),
            (process_acagarwal_mcx_csv, "MCX"),
        ]:
            try:
                tdf = proc_func(output_path)
                if not tdf.empty:
                    copy_from_dataframe(tdf)
            except Exception as e:
                logger.error(f"Error processing {seg_name} CSV: {e}")

        try:
            index_data = fetch_index_list()
            if index_data:
                index_df = process_index_data(index_data)
                copy_from_dataframe(index_df)
        except Exception as e:
            logger.error(f"Error processing Index data: {e}")

        delete_acagarwal_temp_data(output_path)
        return socketio.emit("master_contract_download", {"status": "success", "message": "Successfully Downloaded"})
    except Exception as e:
        logger.error(f"Master contract download failed: {e}")
        return socketio.emit("master_contract_download", {"status": "error", "message": str(e)})


def search_symbols(symbol, exchange):
    return SymToken.query.filter(
        SymToken.symbol.like(f"%{symbol}%"), SymToken.exchange == exchange
    ).all()
