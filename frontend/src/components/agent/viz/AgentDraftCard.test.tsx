import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgentDraftCard } from './AgentDraftCard'

const mockNavigate = vi.fn()
vi.mock('react-router', () => ({
  useNavigate: () => mockNavigate,
}))

const mockStartRun = vi.fn()
vi.mock('@/api/strategy_module', () => ({
  startRun: (...args: any[]) => mockStartRun(...args),
}))

describe('AgentDraftCard', () => {
  const sampleSpec = {
    strategy_id: 101,
    name: '₹100 Premium Seller',
    underlying: 'NIFTY',
    strategy_type: 'option_selling',
    capital_inr: 50000,
    stop_loss_inr: 1500,
    target_profit_inr: 2500,
    max_lots: 1,
    account: 'AC Agarwal (DM933)',
    summary: 'NIFTY current_weekly | 1 lot | SL: ₹1,500 | Target: ₹2,500',
    plain_language: {
      when: 'At 9:16 AM · Mon, Wed, Thu, Fri',
      entry_gates: ['Matches option selling criteria'],
      it_scans: 'Scans NIFTY weekly options, 1 lot max',
      how_it_exits: ['Take profit at +₹2,500', 'Stop loss at -₹1,500', 'Mandatory 15:15 auto-exit'],
    },
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders strategy details, status badges and summary', () => {
    render(<AgentDraftCard spec={sampleSpec} />)

    expect(screen.getByText('₹100 Premium Seller')).toBeInTheDocument()
    expect(screen.getByText('Account: AC Agarwal (DM933)')).toBeInTheDocument()
    expect(screen.getByText('● Paused')).toBeInTheDocument()
    expect(screen.getByText('Practice Mode')).toBeInTheDocument()
    expect(
      screen.getByText('NIFTY current_weekly | 1 lot | SL: ₹1,500 | Target: ₹2,500')
    ).toBeInTheDocument()
  })

  it('deploys to paper mode when deploy button is clicked', async () => {
    mockStartRun.mockResolvedValueOnce({ status: 'success', run_id: 1 })

    render(<AgentDraftCard spec={sampleSpec} />)

    const deployButton = screen.getByRole('button', { name: /Deploy to Paper/i })
    fireEvent.click(deployButton)

    expect(mockStartRun).toHaveBeenCalledWith(101, 'sandbox')

    await waitFor(() => {
      expect(screen.getByText(/Running in Paper Mode/i)).toBeInTheDocument()
    })
  })

  it('expands rules when View Rules button is clicked', () => {
    render(<AgentDraftCard spec={sampleSpec} />)

    const toggleButton = screen.getByRole('button', { name: /View Rules/i })
    fireEvent.click(toggleButton)

    expect(screen.getByText(/At 9:16 AM · Mon, Wed, Thu, Fri/i)).toBeInTheDocument()
    expect(screen.getByText(/Scans NIFTY weekly options, 1 lot max/i)).toBeInTheDocument()
  })
})
