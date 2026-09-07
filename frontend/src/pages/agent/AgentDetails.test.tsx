import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@/test/test-utils'
import type { Order, Strategy, StrategyEvent } from '@/types/strategy_module'
import AgentDetails from './AgentDetails'

const mockStrategy: Strategy = {
  id: 101,
  name: '₹100 Premium Seller',
  strategy_kind: 'batch',
  direction: 'both',
  universe_tab: 'weekly_monthly',
  underlying: 'NIFTY',
  underlying_exchange: 'NFO',
  strategy_type: 'intraday',
  entry_time: '09:16',
  exit_time: '15:15',
  product: 'MIS',
  pricetype: 'MARKET',
  overall_sl_mtm: 1500,
  overall_target_mtm: 2500,
  lock_profit: null,
  trail_sl_to_entry: false,
  legs: [
    {
      id: 1,
      strategy_id: 101,
      leg_id: 'leg_1',
      instrument_type: 'CE',
      strike_offset: 0,
      action: 'SELL',
      lots: 1,
      expiry: 'current_weekly',
      sl_unit: 'points',
      sl_value: null,
      target_unit: 'points',
      target_value: null,
      trail_sl_point: null,
      trail_step_point: null,
    },
  ],
  scheduler: {
    enabled: true,
    days: ['MON', 'WED', 'THU', 'FRI'],
    start_time: '09:16',
    auto_stop_time: '15:15',
    default_mode: 'sandbox',
    // @ts-expect-error test payload
    agent_metadata: {
      category: 'option_selling',
      capital_inr: 50000,
      max_lots: 1,
      plain_language: {
        when: 'At 9:16 AM · Mon, Wed, Thu, Fri',
        entry_gates: ['LTP ₹99 - ₹101 per option', 'Time gate: 9:16 AM IST'],
        it_scans: 'Scans NIFTY weekly options, 1 lot max.',
        how_it_exits: [
          'Take profit at +₹2,500',
          'Stop loss at -₹1,500',
          'Mandatory 3:15 PM auto-exit',
        ],
      },
    },
  },
  live_enabled: false,
  webhook_locked: false,
  webhook_ip_allowlist: null,
  daily_loss_limit_inr: 2000,
  status: 'running',
  current_run_id: 1,
  created_at: '2026-09-07T10:00:00Z',
  updated_at: '2026-09-07T10:00:00Z',
  last_finalized_run: {
    id: 1,
    pnl_realized: 1450,
    stopped_at: '2026-09-07T14:00:00Z',
  },
}

const mockEvents: StrategyEvent[] = [
  {
    id: 1,
    strategy_id: 101,
    run_id: 1,
    ts: '2026-09-07T09:16:05Z',
    kind: 'entry_gate_passed',
    severity: 'info',
    leg_id: null,
    message: 'NIFTY 24500 CE LTP ₹100.20 satisfied entry gate. Limit order placed.',
    payload: null,
  },
]

const mockOrders: Order[] = []

vi.mock('@/api/strategy_module', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/strategy_module')>()
  return {
    ...actual,
    getStrategy: vi.fn(async () => mockStrategy),
    listEvents: vi.fn(async () => mockEvents),
    listOrders: vi.fn(async () => mockOrders),
    buildRoundTrips: vi.fn(() => []),
    useStrategyLive: vi.fn(() => ({
      status: 'connected',
      runId: 1,
      checkpoint: {
        id: 1,
        run_id: 1,
        ts: '2026-09-07T10:00:00Z',
        pnl_realized: 1450,
        pnl_unrealized: 0,
        pnl_total: 1450,
        pnl_peak: 1500,
        pnl_trough: 0,
        lock_floor: null,
        trail_to_entry_active: false,
        leg_state: {},
      },
      legs: [],
      updatedAt: '2026-09-07T10:00:00Z',
      curve: [],
      isFetching: false,
      error: null,
      refresh: vi.fn(),
    })),
    stopRun: vi.fn(async () => ({ run_id: 1, exits: [], stop_pending: false, run_stopped: true })),
    startRun: vi.fn(async () => ({ run_id: 2, mode: 'sandbox', legs: [] })),
    closeAll: vi.fn(async () => ({ run_id: 1, exits: [], stop_pending: false, run_stopped: true })),
    updateStrategy: vi.fn(async (_id, payload) => ({ ...mockStrategy, ...payload })),
    deleteStrategy: vi.fn(async () => {}),
  }
})

vi.mock('@/components/layout/Navbar', () => ({
  Navbar: () => <nav aria-label="Main" />,
}))

function wrap(node: ReactElement) {
  window.history.pushState({}, 'Test', '/agent/my-agents/101')
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Routes>
        <Route path="/agent/my-agents/:id" element={node} />
      </Routes>
    </QueryClientProvider>
  )
}

describe('AgentDetails', () => {
  it('renders plain-language breakdown, safety guards, and live journal feed', async () => {
    wrap(<AgentDetails />)

    // Strategy header
    expect(await screen.findByText('₹100 Premium Seller')).toBeInTheDocument()
    expect(screen.getByText('Watching Market')).toBeInTheDocument()

    // Plain-language rules
    expect(screen.getByText('What this agent does: In plain language')).toBeInTheDocument()
    expect(screen.getByText('At 9:16 AM · Mon, Wed, Thu, Fri')).toBeInTheDocument()
    expect(screen.getByText('Scans NIFTY weekly options, 1 lot max.')).toBeInTheDocument()
    expect(screen.getByText('Take profit at +₹2,500')).toBeInTheDocument()

    // Safety guards
    expect(screen.getByText('Automated Safety Guards')).toBeInTheDocument()
    expect(screen.getByText('Most you can lose per trade')).toBeInTheDocument()
    expect(screen.getByText('Hard daily loss cutoff')).toBeInTheDocument()

    // Live journal feed
    expect(screen.getByText('Live Journal Feed')).toBeInTheDocument()
    expect(
      screen.getByText(/NIFTY 24500 CE LTP ₹100.20 satisfied entry gate/i)
    ).toBeInTheDocument()
  })

  it('opens Ask AI copilot drawer and responds to diagnostic prompts', async () => {
    wrap(<AgentDetails />)

    const askAiBtn = await screen.findByRole('button', { name: /Ask AI/i })
    fireEvent.click(askAiBtn)

    expect(await screen.findByText('AI Agent Copilot')).toBeInTheDocument()
    expect(screen.getByText(/Why hasn't this agent traded today/i)).toBeInTheDocument()
    expect(screen.getByText(/How can I make this agent safer/i)).toBeInTheDocument()

    // Click quick diagnostic prompt
    fireEvent.click(screen.getByText(/Why hasn't this agent traded today/i))
    expect(
      await screen.findByText(/Based on current Symphony XTS market evaluation/i)
    ).toBeInTheDocument()
  })

  it('opens Edit Parameters modal and allows adjusting profit target and stop loss', async () => {
    wrap(<AgentDetails />)

    const editBtn = await screen.findByRole('button', { name: /Edit/i })
    fireEvent.click(editBtn)

    expect(await screen.findByText(/Edit Parameters: ₹100 Premium Seller/i)).toBeInTheDocument()
    expect(screen.getByText(/Take Profit Target \(₹\)/i)).toBeInTheDocument()
    expect(screen.getByText(/Save Parameters/i)).toBeInTheDocument()
  })
})
