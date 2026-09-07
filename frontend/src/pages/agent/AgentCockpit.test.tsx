import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactElement } from 'react'
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@/test/test-utils'
import type { StrategySummary } from '@/types/strategy_module'
import AgentCockpit from './AgentCockpit'

const mockStrategies: StrategySummary[] = [
  {
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
          entry_gates: ['LTP ₹99 - ₹101 per option'],
          it_scans: 'Scans NIFTY weekly options, 1 lot max.',
          how_it_exits: ['Take profit at +₹2,500', 'Stop loss at -₹1,500'],
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
  },
  {
    id: 102,
    name: 'Nifty Dip Buyer',
    strategy_kind: 'batch',
    direction: 'both',
    universe_tab: 'weekly_monthly',
    underlying: 'NIFTY',
    underlying_exchange: 'NFO',
    strategy_type: 'intraday',
    entry_time: '09:30',
    exit_time: '15:15',
    product: 'MIS',
    pricetype: 'MARKET',
    overall_sl_mtm: 1000,
    overall_target_mtm: 2000,
    lock_profit: null,
    trail_sl_to_entry: false,
    scheduler: null,
    live_enabled: false,
    webhook_locked: false,
    webhook_ip_allowlist: null,
    daily_loss_limit_inr: 1500,
    status: 'paused',
    current_run_id: null,
    created_at: '2026-09-07T10:00:00Z',
    updated_at: '2026-09-07T10:00:00Z',
  },
]

vi.mock('@/api/strategy_module', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/api/strategy_module')>()
  return {
    ...actual,
    listStrategies: vi.fn(async () => mockStrategies),
    useStrategyListPnl: vi.fn(() => new Map([[101, { total: 1450, realized: 1450, unrealized: 0, finalized: true }]])),
    stopRun: vi.fn(async () => ({ run_id: 1, exits: [], stop_pending: false, run_stopped: true })),
    startRun: vi.fn(async () => ({ run_id: 2, mode: 'sandbox', legs: [] })),
    closeAll: vi.fn(async () => ({ run_id: 1, exits: [], stop_pending: false, run_stopped: true })),
  }
})

vi.mock('@/components/layout/Navbar', () => ({
  Navbar: () => <nav aria-label="Main" />,
}))

function wrap(node: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>)
}

describe('AgentCockpit', () => {
  it('renders the cockpit overview, traffic light badges, and agent cards', async () => {
    wrap(<AgentCockpit />)

    expect(await screen.findByText('₹100 Premium Seller')).toBeInTheDocument()
    expect(screen.getByText('Nifty Dip Buyer')).toBeInTheDocument()

    // Traffic light badges
    expect(screen.getByText('Watching')).toBeInTheDocument()
    expect(screen.getByText('Paused')).toBeInTheDocument()

    // Rupee P&L and safety limits
    expect(screen.getAllByText('₹+1450.00').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('₹2,000')).toBeInTheDocument()
  })

  it('triggers emergency square off dialog with confirmation button', async () => {
    wrap(<AgentCockpit />)

    const squareOffButtons = await screen.findAllByRole('button', { name: /Square Off/i })
    expect(squareOffButtons.length).toBeGreaterThan(0)
    fireEvent.click(squareOffButtons[0])

    // Verify dialog pops up
    expect(await screen.findByText(/Emergency Square Off: ₹100 Premium Seller/i)).toBeInTheDocument()
    expect(screen.getByText(/Confirm Square Off All/i)).toBeInTheDocument()
  })
})
