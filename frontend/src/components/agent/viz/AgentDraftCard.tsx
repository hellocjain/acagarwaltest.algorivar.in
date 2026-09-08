import { CheckCircle2, ChevronDown, ChevronUp, Loader2, Play, ShieldCheck, Zap } from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router'
import { startRun } from '@/api/strategy_module'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

export interface AgentDraftCardProps {
  spec: {
    strategy_id: number
    name: string
    strategy_category?: string
    underlying?: string
    universe?: string
    instrument_preference?: string
    option_type?: string
    strike_mode?: string
    max_premium_per_trade_inr?: number
    premium_target_pct?: number
    premium_sl_pct?: number
    strategy_type?: string
    capital_inr?: number
    capital_per_trade_inr?: number
    max_concurrent_positions?: number
    stop_loss_inr?: number
    target_profit_inr?: number
    max_lots?: number
    account?: string
    summary?: string
    condition_tree?: any
    plain_language?: {
      when?: string
      entry_gates?: string[]
      it_scans?: string
      how_it_exits?: string[]
    }
  }
  title?: string
  className?: string
}

function extractLeafSummary(node: any): Array<{ label: string; type: string }> {
  if (!node) return []
  if (Array.isArray(node.rules)) {
    return node.rules.flatMap((r: any) => extractLeafSummary(r))
  }
  if (node.type === 'indicator') {
    const p = node.params ? Object.values(node.params)[0] : ''
    return [{ label: `${node.indicator}${p ? `(${p})` : ''} ${node.comp || '<'} ${node.value}`, type: 'indicator' }]
  }
  if (node.type === 'candlestick') {
    return [{ label: `${node.pattern?.replace('_', ' ').toLowerCase()} pattern`, type: 'candlestick' }]
  }
  if (node.type === 'indicator_cross') {
    return [{ label: `${node.left?.indicator || 'Price'} ${node.comp} ${node.right?.indicator || 'MA'}`, type: 'cross' }]
  }
  if (node.type === 'price') {
    return [{ label: `Price ${node.comp || '>'} ${node.value}`, type: 'price' }]
  }
  return [{ label: JSON.stringify(node), type: 'rule' }]
}

export function AgentDraftCard({ spec, className }: AgentDraftCardProps) {
  const navigate = useNavigate()
  const [deployState, setDeployState] = useState<'draft' | 'deploying' | 'running' | 'error'>('draft')
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [detailsExpanded, setDetailsExpanded] = useState(false)

  const handleDeploy = async () => {
    try {
      setDeployState('deploying')
      setErrorMessage(null)
      await startRun(spec.strategy_id, 'sandbox')
      setDeployState('running')
    } catch (err: any) {
      setDeployState('error')
      setErrorMessage(err?.message || 'Failed to deploy strategy in paper mode.')
    }
  }

  const handleReview = () => {
    navigate(`/agent/my-agents/${spec.strategy_id}`)
  }

  return (
    <div
      className={cn(
        'my-3 w-full rounded-xl border border-border bg-card p-4 shadow-sm transition-all hover:border-primary/40',
        className
      )}
    >
      {/* Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Zap className="h-4 w-4" />
          </div>
          <div>
            <h4 className="text-sm font-semibold tracking-tight text-foreground">{spec.name}</h4>
            <p className="text-[11px] text-muted-foreground">Account: {spec.account || 'AC Agarwal (DM933)'}</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          {spec.strategy_category === 'scanner' || spec.universe ? (
            <>
              <span className="rounded-full bg-purple-500/10 px-2 py-0.5 text-[10px] font-medium text-purple-600 dark:text-purple-400">
                {spec.instrument_preference === 'options'
                  ? `${spec.universe || 'F&O'} Options Scanner`
                  : spec.instrument_preference === 'futures'
                  ? `${spec.universe || 'F&O'} Futures Scanner`
                  : `${spec.universe || 'NIFTY 500'} Scanner`}
              </span>
              {spec.instrument_preference === 'options' && (
                <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-600 dark:text-amber-400">
                  Rollover Shield
                </span>
              )}
            </>
          ) : (
            <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
              {spec.underlying || 'NIFTY'} Options
            </span>
          )}
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-[10px] font-medium',
              deployState === 'running'
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
            )}
          >
            ● {deployState === 'running' ? 'Active' : 'Paused'}
          </span>
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
            Auto
          </span>
          <span className="rounded-full bg-blue-500/10 px-2 py-0.5 text-[10px] font-medium text-blue-600 dark:text-blue-400">
            Practice Mode
          </span>
        </div>
      </div>

      {/* Summary Row */}
      <div className="py-2.5">
        <p className="font-mono text-xs text-muted-foreground">
          {spec.summary ||
            (spec.instrument_preference === 'options'
              ? `${spec.universe || 'F&O'} Stock Options (${spec.option_type || 'CE'} ATM) | Max ₹${(spec.max_premium_per_trade_inr || 15000).toLocaleString('en-IN')}/trade | Max ${spec.max_concurrent_positions || 3} concurrent`
              : spec.strategy_category === 'scanner' || spec.universe
              ? `${spec.universe || 'NIFTY 500'} Scanner | Max ${spec.max_concurrent_positions || 5} concurrent | ₹${(spec.capital_per_trade_inr || 10000).toLocaleString('en-IN')}/trade`
              : `${spec.underlying || 'NIFTY'} current_weekly | ${spec.max_lots || 1} lot | SL: ₹${spec.stop_loss_inr} | TGT: ₹${spec.target_profit_inr}`)}
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 pt-1">
        {deployState === 'running' ? (
          <Button size="sm" variant="outline" className="gap-1.5 border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-50/30" disabled>
            <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
            Running in Paper Mode
          </Button>
        ) : (
          <Button
            size="sm"
            onClick={handleDeploy}
            disabled={deployState === 'deploying'}
            className="gap-1.5 bg-primary font-medium text-primary-foreground hover:bg-primary/90"
          >
            {deployState === 'deploying' ? (
              <>
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Deploying…
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5" />
                Deploy to Paper
              </>
            )}
          </Button>
        )}

        <Button size="sm" variant="secondary" onClick={handleReview} className="text-xs">
          Review Details
        </Button>

        <Button
          size="sm"
          variant="ghost"
          onClick={() => setDetailsExpanded((prev) => !prev)}
          className="ml-auto text-xs text-muted-foreground hover:text-foreground"
        >
          {detailsExpanded ? (
            <>
              Hide Rules <ChevronUp className="ml-1 h-3.5 w-3.5" />
            </>
          ) : (
            <>
              View Rules <ChevronDown className="ml-1 h-3.5 w-3.5" />
            </>
          )}
        </Button>
      </div>

      {errorMessage && (
        <div className="mt-2 rounded-md bg-destructive/10 p-2 text-xs text-destructive">
          {errorMessage}
        </div>
      )}

      {/* Collapsible Parameters Table */}
      {detailsExpanded && (spec.plain_language || spec.condition_tree) && (
        <div className="mt-3 space-y-2 rounded-lg border border-border/80 bg-muted/30 p-3 text-xs">
          {spec.plain_language?.when && (
            <div className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-3.5 w-3.5 text-primary shrink-0" />
              <div className="space-y-1">
                <span className="font-semibold text-foreground">WHEN: </span>
                <span className="text-muted-foreground">{spec.plain_language.when}</span>
              </div>
            </div>
          )}

          {spec.plain_language?.entry_gates && spec.plain_language.entry_gates.length > 0 && (
            <div className="pl-5 text-muted-foreground">
              <span className="font-semibold text-foreground">ENTRY GATES: </span>
              {spec.plain_language.entry_gates.join(' · ')}
            </div>
          )}

          {spec.condition_tree && (
            <div className="pl-5 pt-1 space-y-1">
              <span className="font-semibold text-foreground">CONDITION LOGIC (AST): </span>
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                <span className="inline-flex items-center rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-medium text-primary">
                  TREE: {spec.condition_tree.op || 'AND'}
                </span>
                {extractLeafSummary(spec.condition_tree).map((leaf, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center rounded-md border border-border bg-background/80 px-2 py-0.5 text-[10px] font-mono text-foreground"
                  >
                    {leaf.label}
                  </span>
                ))}
              </div>
            </div>
          )}

          {spec.plain_language?.it_scans && (
            <div className="pl-5 text-muted-foreground">
              <span className="font-semibold text-foreground">IT SCANS: </span>
              {spec.plain_language.it_scans}
            </div>
          )}

          {spec.plain_language?.how_it_exits && spec.plain_language.how_it_exits.length > 0 && (
            <div className="pl-5 text-muted-foreground">
              <span className="font-semibold text-foreground">HOW IT EXITS: </span>
              {spec.plain_language.how_it_exits.join(' · ')}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
