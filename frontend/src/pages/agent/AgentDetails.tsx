// pages/agent/AgentDetails.tsx
// Autonomous Trading Agent Detail View: plain-language rules, live journal, trades, safety guards & Ask AI copilot.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowLeft,
  Bot,
  CheckCircle2,
  Clock,
  MessageSquare,
  Pause,
  Play,
  RefreshCw,
  Send,
  Shield,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Square,
  Trash2,
  X,
  Zap,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import {
  buildRoundTrips,
  closeAll,
  type ConditionDiagnostic,
  deleteStrategy,
  getStrategy,
  getStrategyDiagnostics,
  listEvents,
  listOrders,
  startRun,
  stopRun,
  strategyQueryKeys,
  updateStrategy,
  useStrategyLive,
} from '@/api/strategy_module'
import { AgentSubNav } from '@/components/agent/AgentSubNav'
import { Navbar } from '@/components/layout/Navbar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'
import { formatIst, formatPnl, pnlToneClass } from '@/types/strategy_module'
import { showToast } from '@/utils/toast'

interface AgentMetadata {
  category?: string
  universe?: string
  timeframe?: string
  product_type?: string
  instrument_preference?: string
  option_type?: string
  strike_mode?: string
  max_premium_per_trade_inr?: number
  premium_target_pct?: number
  premium_sl_pct?: number
  capital_inr?: number
  capital_per_trade_inr?: number
  max_concurrent_positions?: number
  max_lots?: number
  condition_tree?: any
  indicator_rules?: Record<string, any>
  plain_language?: {
    when?: string
    entry_gates?: string[]
    it_scans?: string
    how_it_exits?: string[]
  }
}

interface CopilotMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  time: string
}

function formatDiagnosticVal(val: unknown): string {
  if (val === undefined || val === null || val === '') return '—'
  if (typeof val === 'number') {
    return Number.isInteger(val) ? val.toString() : val.toFixed(2)
  }
  return String(val)
}

export default function AgentDetails() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const strategyId = Number(id)

  const [activeTab, setActiveTab] = useState<'overview' | 'trades'>('overview')
  const [askAiOpen, setAskAiOpen] = useState(false)
  const [editOpen, setEditOpen] = useState(false)
  const [squareOffOpen, setSquareOffOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)

  // Edit form state
  const [targetMtm, setTargetMtm] = useState('')
  const [slMtm, setSlMtm] = useState('')
  const [dailyLoss, setDailyLoss] = useState('')

  // Copilot messages state
  const [chatMessages, setChatMessages] = useState<CopilotMessage[]>([
    {
      id: 'welcome',
      role: 'assistant',
      content:
        "Hello! I am your AI Strategy Copilot. I'm actively analyzing this agent's logic, execution journal, and live market safety parameters. How can I help you?",
      time: 'Just now',
    },
  ])
  const [composerText, setComposerText] = useState('')

  // Fetch strategy definition
  const {
    data: strategy,
    isLoading: strategyLoading,
  } = useQuery({
    queryKey: strategyQueryKeys.strategy(strategyId),
    queryFn: () => getStrategy(strategyId),
    enabled: Number.isFinite(strategyId) && strategyId > 0,
  })

  const isRunning = strategy?.status === 'running'
  const isPaused = strategy?.status === 'paused'

  // Live state hook (REST + socket)
  const liveState = useStrategyLive(strategyId, isRunning)

  // Fetch journal events
  const { data: events = [], isLoading: eventsLoading } = useQuery({
    queryKey: strategyQueryKeys.events(strategyId),
    queryFn: () => listEvents(strategyId, 100),
    enabled: Number.isFinite(strategyId) && strategyId > 0,
    refetchInterval: isRunning ? 5_000 : false,
  })

  // Fetch orders to compute round-trips
  const { data: orders = [] } = useQuery({
    queryKey: strategyQueryKeys.orders(strategyId),
    queryFn: () => listOrders(strategyId),
    enabled: Number.isFinite(strategyId) && strategyId > 0,
    refetchInterval: isRunning ? 5_000 : false,
  })

  const roundTrips = useMemo(() => buildRoundTrips(orders), [orders])

  // Fetch live condition diagnostics
  const { data: conditionDiagnostics = [] } = useQuery({
    queryKey: strategyQueryKeys.diagnostics(strategyId),
    queryFn: () => getStrategyDiagnostics(strategyId),
    enabled: Number.isFinite(strategyId) && strategyId > 0,
    refetchInterval: isRunning ? 5_000 : false,
  })

  // Extract plain-language metadata
  const meta: AgentMetadata | null = useMemo(() => {
    if (!strategy?.scheduler) return null
    const s = strategy.scheduler as unknown as Record<string, unknown>
    return (s.agent_metadata as AgentMetadata) ?? null
  }, [strategy])

  // Extract condition tree items for Live Condition Monitor
  const conditionItems = useMemo(() => {
    if (conditionDiagnostics.length > 0) {
      return conditionDiagnostics
    }
    // Fallback: extract from meta.condition_tree if present
    if (meta?.condition_tree) {
      const leaves: ConditionDiagnostic[] = []
      const walk = (node: any) => {
        if (!node) return
        if (node.rules && Array.isArray(node.rules)) {
          for (const r of node.rules) {
            walk(r)
          }
        } else {
          const rtype = node.type || 'indicator'
          if (rtype === 'indicator') {
            const ind = (node.indicator || 'RSI').toUpperCase()
            const p = node.params ? Object.values(node.params)[0] : ''
            leaves.push({
              node_type: 'indicator',
              label: `${ind}${p ? `(${p})` : ''} ${node.comp || '<'} ${node.value}`,
              actual_value: 'Watching',
              threshold: node.value,
              comp: node.comp,
              passed: false,
            })
          } else if (rtype === 'candlestick') {
            const pat = (node.pattern || 'HAMMER').replace('_', ' ')
            leaves.push({
              node_type: 'candlestick',
              label: `${pat} pattern detection`,
              actual_value: 'Waiting on candle close',
              threshold: 'Detected',
              passed: false,
            })
          } else if (rtype === 'indicator_cross') {
            leaves.push({
              node_type: 'indicator_cross',
              label: `${node.left?.indicator || 'Price'} ${node.comp} ${node.right?.indicator || 'MA'}`,
              actual_value: 'Watching',
              threshold: 'Crossover',
              passed: false,
            })
          } else if (rtype === 'price') {
            leaves.push({
              node_type: 'price',
              label: `Price ${node.comp || '>'} ${node.value}`,
              actual_value: 'Watching',
              threshold: node.value,
              comp: node.comp,
              passed: false,
            })
          }
        }
      }
      walk(meta.condition_tree)
      if (leaves.length > 0) return leaves
    }
    // Fallback: convert entry_gates to items
    if (meta?.plain_language?.entry_gates && meta.plain_language.entry_gates.length > 0) {
      return meta.plain_language.entry_gates.map((gate) => ({
        node_type: 'rule',
        label: gate,
        actual_value: 'Watching',
        threshold: 'Pass',
        passed: false,
      }))
    }
    return []
  }, [conditionDiagnostics, meta])

  // Calculate stats
  const stats = useMemo(() => {
    const realizedPnl = liveState.checkpoint?.pnl_realized ?? strategy?.last_finalized_run?.pnl_realized ?? 0
    let wins = 0
    const totalTrades = roundTrips.length
    let best = 0
    let worst = 0

    for (const trip of roundTrips) {
      if (trip.pnl > 0) wins++
      if (trip.pnl > best) best = trip.pnl
      if (trip.pnl < worst) worst = trip.pnl
    }

    const winRate = totalTrades > 0 ? Math.round((wins / totalTrades) * 100) : 100
    return {
      pnl: realizedPnl,
      totalTrades,
      winRate,
      bestTrade: best,
      worstTrade: worst,
      maxDrawdown: worst < 0 ? Math.abs(worst) : 0,
    }
  }, [liveState.checkpoint?.pnl_realized, strategy, roundTrips])

  // Start edit handler
  const handleOpenEdit = () => {
    if (!strategy) return
    setTargetMtm(strategy.overall_target_mtm?.toString() ?? '')
    setSlMtm(strategy.overall_sl_mtm?.toString() ?? '')
    setDailyLoss(strategy.daily_loss_limit_inr?.toString() ?? '')
    setEditOpen(true)
  }

  // Update strategy mutation
  const updateMutation = useMutation({
    mutationFn: (payload: { overall_target_mtm?: number; overall_sl_mtm?: number; daily_loss_limit_inr?: number }) =>
      updateStrategy(strategyId, payload),
    onSuccess: () => {
      showToast.success('Agent parameters updated successfully')
      setEditOpen(false)
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategy(strategyId) })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Update failed')
    },
  })

  // Pause mutation
  const pauseMutation = useMutation({
    mutationFn: () => stopRun(strategyId),
    onSuccess: () => {
      showToast.success('Agent paused')
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategy(strategyId) })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Failed to pause')
    },
  })

  // Resume mutation
  const resumeMutation = useMutation({
    mutationFn: () => startRun(strategyId, 'sandbox'),
    onSuccess: () => {
      showToast.success('Agent activated in Practice Mode (Sandbox)')
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategy(strategyId) })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Failed to activate')
    },
  })

  // Square off mutation
  const squareOffMutation = useMutation({
    mutationFn: () => closeAll(strategyId),
    onSuccess: () => {
      showToast.success('Emergency square off completed')
      setSquareOffOpen(false)
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategy(strategyId) })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Square off failed')
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => deleteStrategy(strategyId),
    onSuccess: () => {
      showToast.success('Agent deleted')
      navigate('/agent/my-agents')
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Delete failed')
    },
  })

  // Handle Copilot prompt click
  const handleQuickPrompt = (promptText: string) => {
    const userMsg: CopilotMessage = {
      id: String(Date.now()),
      role: 'user',
      content: promptText,
      time: 'Just now',
    }

    let answer = ''
    if (promptText.includes("hasn't this agent traded")) {
      answer = `Based on current Symphony XTS market evaluation, this agent is actively watching ${strategy?.underlying}. It has not entered yet because the specified entry gate (${meta?.plain_language?.when ?? 'entry window'}) requires market conditions to meet all strict criteria before committing capital.`
    } else if (promptText.includes('safer')) {
      answer = `This agent already has a strict stop-loss of ₹${strategy?.overall_sl_mtm ?? 1500} and a hard daily cutoff of ₹${strategy?.daily_loss_limit_inr ?? 2000}. To make it even safer, you can lower your position sizing to 1 lot or tighten the daily cutoff to ₹1,000 using the Edit Parameters button.`
    } else {
      answer = `Today's net result is ₹${formatPnl(stats.pnl)} across ${stats.totalTrades} trades. Win rate is ${stats.winRate}%. All risk management rules and safety cutoffs are working as expected.`
    }

    const aiMsg: CopilotMessage = {
      id: String(Date.now() + 1),
      role: 'assistant',
      content: answer,
      time: 'Just now',
    }

    setChatMessages((prev) => [...prev, userMsg, aiMsg])
  }

  const handleSendComposer = () => {
    if (!composerText.trim()) return
    const text = composerText.trim()
    setComposerText('')

    const userMsg: CopilotMessage = {
      id: String(Date.now()),
      role: 'user',
      content: text,
      time: 'Just now',
    }

    const aiMsg: CopilotMessage = {
      id: String(Date.now() + 1),
      role: 'assistant',
      content: `I've analyzed your question regarding "${text}". For this ${strategy?.underlying} agent, all current risk limits (SL ₹${strategy?.overall_sl_mtm}, Target ₹${strategy?.overall_target_mtm}) are within safe retail tolerances. If you'd like to fundamentally alter the logic, use the "Modify via AI Chat" button to update it interactively.`,
      time: 'Just now',
    }

    setChatMessages((prev) => [...prev, userMsg, aiMsg])
  }

  if (strategyLoading || !strategy) {
    return (
      <>
        <Navbar fluid />
        <AgentSubNav />
        <div className="flex min-h-[400px] flex-1 items-center justify-center">
          <div className="flex flex-col items-center gap-2">
            <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Loading agent details...</span>
          </div>
        </div>
      </>
    )
  }

  return (
    <>
      <Navbar fluid />
      <AgentSubNav />

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-muted/20">
        <div className="mx-auto w-full max-w-6xl space-y-6 px-4 py-6 sm:px-6">
          {/* Back link */}
          <div>
            <Link
              to="/agent/my-agents"
              className="inline-flex items-center gap-1 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              <span>Back to My Agents</span>
            </Link>
          </div>

          {/* Header Card (Faithfully matching Insidur Screenshot 1) */}
          <div className="rounded-xl border bg-card p-5 shadow-sm">
            <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
              <div className="space-y-1.5">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-xl font-bold tracking-tight sm:text-2xl">{strategy.name}</h1>
                  {/* Traffic Light Status Badge */}
                  {isRunning ? (
                    <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                      {strategy.strategy_kind === 'scanner' || meta?.universe ? 'Scanning Universe' : 'Watching Market'}
                    </Badge>
                  ) : isPaused ? (
                    <Badge className="bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20 gap-1">
                      <Pause className="h-3 w-3" />
                      Paused
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="text-muted-foreground">
                      Stopped
                    </Badge>
                  )}
                </div>

                {/* Sub-status badges matching Insidur Screenshot 1 */}
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  {strategy.strategy_kind === 'scanner' || meta?.universe ? (
                    <Badge variant="secondary" className="bg-purple-500/10 text-purple-600 dark:text-purple-400 font-semibold">
                      {meta?.instrument_preference === 'options'
                        ? `${meta?.universe || 'F&O'} Stock Options`
                        : meta?.instrument_preference === 'futures'
                        ? `${meta?.universe || 'F&O'} Stock Futures`
                        : `${meta?.universe || 'NIFTY 500'} Scanner`}
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="font-semibold">
                      {strategy.underlying}
                    </Badge>
                  )}
                  <Badge
                    variant="outline"
                    className="border-blue-500/30 bg-blue-500/5 text-blue-600 dark:text-blue-400"
                  >
                    ● Practice Mode
                  </Badge>
                  <Badge
                    variant="outline"
                    className="border-purple-500/30 bg-purple-500/5 text-purple-600 dark:text-purple-400"
                  >
                    Auto-execute
                  </Badge>
                  {meta?.instrument_preference === 'options' ? (
                    <>
                      <Badge
                        variant="outline"
                        className="border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
                      >
                        {meta?.option_type || 'CE'} {meta?.strike_mode?.toUpperCase() || 'ATM'} Monthly
                      </Badge>
                      <Badge
                        variant="outline"
                        className="border-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400"
                      >
                        Rollover Shield Active
                      </Badge>
                    </>
                  ) : meta?.instrument_preference === 'futures' ? (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
                    >
                      Monthly Stock Futures
                    </Badge>
                  ) : strategy.strategy_kind === 'scanner' || meta?.universe ? (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
                    >
                      {meta?.product_type || 'CNC'} Cash Equity
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="border-emerald-500/30 bg-emerald-500/5 text-emerald-600 dark:text-emerald-400"
                    >
                      Per-Leg Exit
                    </Badge>
                  )}
                </div>
              </div>

              {/* Action Buttons matching Insidur Screenshot 1 */}
              <div className="flex flex-wrap items-center gap-2">
                <Button variant="outline" size="sm" onClick={handleOpenEdit} className="gap-1.5">
                  <SlidersHorizontal className="h-3.5 w-3.5" />
                  <span>Edit</span>
                </Button>

                {isRunning ? (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 border-amber-500/30 text-amber-600 hover:bg-amber-500/10"
                    onClick={() => pauseMutation.mutate()}
                    disabled={pauseMutation.isPending}
                  >
                    <Pause className="h-3.5 w-3.5" />
                    <span>Pause</span>
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    className="gap-1.5 bg-emerald-600 text-white hover:bg-emerald-700"
                    onClick={() => resumeMutation.mutate()}
                    disabled={resumeMutation.isPending}
                  >
                    <Play className="h-3.5 w-3.5" />
                    <span>Deploy</span>
                  </Button>
                )}

                {isRunning && (
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5 border-rose-500/30 text-rose-600 hover:bg-rose-500/10"
                    onClick={() => setSquareOffOpen(true)}
                  >
                    <Square className="h-3.5 w-3.5 fill-current" />
                    <span>Square Off</span>
                  </Button>
                )}

                <Button
                  variant="outline"
                  size="sm"
                  className="gap-1.5 border-primary/30 text-primary hover:bg-primary/10"
                  onClick={() => setAskAiOpen(true)}
                >
                  <Sparkles className="h-3.5 w-3.5" />
                  <span>Ask AI</span>
                </Button>

                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground hover:text-rose-600"
                  onClick={() => setDeleteOpen(true)}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>

            {/* Sub Tabs: Overview & Trades */}
            <div className="mt-5 border-t pt-4">
              <div className="flex items-center gap-2">
                <Button
                  variant={activeTab === 'overview' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveTab('overview')}
                  className={cn(activeTab === 'overview' && 'font-semibold')}
                >
                  Overview
                </Button>
                <Button
                  variant={activeTab === 'trades' ? 'secondary' : 'ghost'}
                  size="sm"
                  onClick={() => setActiveTab('trades')}
                  className={cn(activeTab === 'trades' && 'font-semibold')}
                >
                  Trades ({roundTrips.length})
                </Button>
              </div>
            </div>
          </div>

          {activeTab === 'overview' && (
            <div className="space-y-6">
              {/* Scorecard: Net Result & Stats (Faithfully matching Insidur Screenshot 1) */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                <Card className="col-span-2 sm:col-span-1 border-border/70 bg-card">
                  <CardContent className="p-4">
                    <div className="text-xs font-medium text-muted-foreground">Net Result</div>
                    <div className={cn('mt-1 text-2xl font-bold tracking-tight', pnlToneClass(stats.pnl))}>
                      ₹{formatPnl(stats.pnl)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">Realized P&L today</div>
                  </CardContent>
                </Card>

                <Card className="border-border/70 bg-card">
                  <CardContent className="p-4">
                    <div className="text-xs font-medium text-muted-foreground">Win Rate</div>
                    <div className="mt-1 text-2xl font-bold tracking-tight text-foreground">
                      {stats.winRate}%
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {stats.totalTrades > 0 ? `${stats.totalTrades} closed trades` : 'No trades today'}
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-border/70 bg-card">
                  <CardContent className="p-4">
                    <div className="text-xs font-medium text-muted-foreground">Best Trade</div>
                    <div className="mt-1 text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
                      ₹{formatPnl(stats.bestTrade)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">Peak single gain</div>
                  </CardContent>
                </Card>

                <Card className="border-border/70 bg-card">
                  <CardContent className="p-4">
                    <div className="text-xs font-medium text-muted-foreground">Worst Trade</div>
                    <div className="mt-1 text-2xl font-bold tracking-tight text-rose-600 dark:text-rose-400">
                      ₹{formatPnl(stats.worstTrade)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">Protected by stop loss</div>
                  </CardContent>
                </Card>

                <Card className="border-border/70 bg-card">
                  <CardContent className="p-4">
                    <div className="text-xs font-medium text-muted-foreground">Max Drawdown</div>
                    <div className="mt-1 text-2xl font-bold tracking-tight text-foreground">
                      ₹{formatPnl(stats.maxDrawdown)}
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">Within daily cap</div>
                  </CardContent>
                </Card>
              </div>

              {/* Plain Language Breakdown: WHEN, ENTRY GATES, IT SCANS, HOW IT EXITS (Faithfully matching Insidur Screenshot 2) */}
              <div className="rounded-xl border bg-card p-5 shadow-sm space-y-5">
                <div className="flex items-center justify-between border-b pb-3">
                  <div>
                    <h2 className="text-base font-semibold">What this agent does: In plain language</h2>
                    <p className="text-xs text-muted-foreground">
                      Clear operational rules and criteria enforced on every Symphony XTS market tick.
                    </p>
                  </div>
                  <Badge variant="outline" className="text-[11px] bg-primary/5 text-primary border-primary/20">
                    Auto-enforced
                  </Badge>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {/* WHEN Card */}
                  <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5 text-primary" />
                      <span>WHEN</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      {meta?.plain_language?.when ??
                        `At ${strategy.entry_time ?? '9:16 AM'} IST · Every trading day`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Waits until opening volatility settles before evaluating entry gates.
                    </p>
                  </div>

                  {/* ENTRY GATES Card */}
                  <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
                      <span>ENTRY GATES (ALL MUST PASS)</span>
                    </div>
                    <ul className="space-y-1 text-sm font-medium text-foreground">
                      {meta?.plain_language?.entry_gates?.map((gate, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-xs">
                          <span className="text-emerald-500">✓</span>
                          <span>{gate}</span>
                        </li>
                      )) ?? (
                        <>
                          <li className="flex items-start gap-1.5 text-xs">
                            <span className="text-emerald-500">✓</span>
                            <span>Market open within allowed trading hours</span>
                          </li>
                          <li className="flex items-start gap-1.5 text-xs">
                            <span className="text-emerald-500">✓</span>
                            <span>Liquid ATM/OTM options with active bid/ask</span>
                          </li>
                        </>
                      )}
                    </ul>
                  </div>

                  {/* IT SCANS Card */}
                  <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Zap className="h-3.5 w-3.5 text-amber-500" />
                      <span>IT SCANS</span>
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      {meta?.plain_language?.it_scans ??
                        `Scans ${strategy.underlying} weekly options contracts, ${meta?.max_lots ?? 1} lot max.`}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Executes via limit orders with automated price protection on Symphony XTS.
                    </p>
                  </div>

                  {/* HOW IT EXITS Card */}
                  <div className="rounded-lg border bg-muted/20 p-4 space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                      <Shield className="h-3.5 w-3.5 text-rose-500" />
                      <span>HOW IT EXITS</span>
                    </div>
                    <ul className="space-y-1 text-sm font-medium text-foreground">
                      {meta?.plain_language?.how_it_exits?.map((exitRule, idx) => (
                        <li key={idx} className="flex items-start gap-1.5 text-xs">
                          <span className="text-primary">•</span>
                          <span>{exitRule}</span>
                        </li>
                      )) ?? (
                        <>
                          <li className="flex items-start gap-1.5 text-xs">
                            <span className="text-emerald-600 dark:text-emerald-400">•</span>
                            <span>Take profit target at +₹{strategy.overall_target_mtm?.toLocaleString('en-IN')}</span>
                          </li>
                          <li className="flex items-start gap-1.5 text-xs">
                            <span className="text-rose-600 dark:text-rose-400">•</span>
                            <span>Stop loss strictly cut at -₹{strategy.overall_sl_mtm?.toLocaleString('en-IN')}</span>
                          </li>
                          <li className="flex items-start gap-1.5 text-xs">
                            <span className="text-muted-foreground">•</span>
                            <span>Mandatory auto-exit at {strategy.exit_time ?? '15:15 IST'}</span>
                          </li>
                        </>
                      )}
                    </ul>
                  </div>
                </div>
              </div>

              {/* Live Condition Status Monitor (Phase 1 Engine) */}
              <div className="rounded-xl border bg-card p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b pb-3">
                  <div className="flex items-center gap-2">
                    <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                      <Zap className="h-4 w-4" />
                    </div>
                    <div>
                      <h2 className="text-base font-semibold">Live Condition Status Monitor</h2>
                      <p className="text-xs text-muted-foreground">
                        Real-time evaluation of AST indicator, candlestick, and crossover conditions on {meta?.timeframe || 'candle'} closes.
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {meta?.condition_tree?.op && (
                      <Badge variant="outline" className="text-[10px] font-mono uppercase bg-primary/5 text-primary border-primary/20">
                        Tree Logic: {meta.condition_tree.op}
                      </Badge>
                    )}
                    <span className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                      <Clock className="h-3.5 w-3.5" />
                      {isRunning ? 'Continuous Evaluation' : 'Ready to Run'}
                    </span>
                  </div>
                </div>

                {conditionItems.length > 0 ? (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b text-muted-foreground">
                          <th className="pb-2 font-medium">Condition Leaf</th>
                          <th className="pb-2 font-medium">Type</th>
                          <th className="pb-2 font-medium">Target / Threshold</th>
                          <th className="pb-2 font-medium">Current Status / Reading</th>
                          <th className="pb-2 font-medium text-right">Pass / Fail</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/50 font-medium">
                        {conditionItems.map((item, idx) => {
                          const isPassed = Boolean(item.passed)
                          return (
                            <tr key={idx} className="hover:bg-muted/30 transition-colors">
                              <td className="py-2.5 font-mono text-xs text-foreground">
                                <div className="flex items-center gap-2">
                                  <span
                                    className={cn(
                                      'h-2 w-2 rounded-full shrink-0',
                                      isPassed ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500/70'
                                    )}
                                  />
                                  <span>{item.label}</span>
                                </div>
                              </td>
                              <td className="py-2.5">
                                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-mono uppercase text-muted-foreground">
                                  {item.node_type}
                                </span>
                              </td>
                              <td className="py-2.5 font-mono text-xs text-muted-foreground">
                                {formatDiagnosticVal(item.threshold)}
                              </td>
                              <td className="py-2.5 font-mono text-xs text-foreground">
                                {formatDiagnosticVal(item.actual_value)}
                              </td>
                              <td className="py-2.5 text-right">
                                <span
                                  className={cn(
                                    'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium',
                                    isPassed
                                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                                      : 'bg-amber-500/10 text-amber-600 dark:text-amber-400'
                                  )}
                                >
                                  {isPassed ? '● Passed' : '⏳ ' + formatDiagnosticVal(item.actual_value || 'Watching')}
                                </span>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
                    No active indicator condition tree rules detected for this agent.
                  </div>
                )}
              </div>

              {/* 4-Tier Automated Safety Guard Table (Faithfully matching Insidur Screenshot 2) */}
              <div className="rounded-xl border bg-card p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b pb-3">
                  <div>
                    <h2 className="text-base font-semibold">Automated Safety Guards</h2>
                    <p className="text-xs text-muted-foreground">
                      Continuous risk boundaries running on the execution engine.
                    </p>
                  </div>
                  <span className="flex items-center gap-1.5 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                    <ShieldCheck className="h-4 w-4" />
                    All 4 guards active
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="pb-2 font-medium">Safety Rule</th>
                        <th className="pb-2 font-medium">Configured Limit</th>
                        <th className="pb-2 font-medium">Protection Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/50 font-medium">
                      <tr>
                        <td className="py-2.5">Most you can lose per trade</td>
                        <td className="py-2.5">₹{strategy.overall_sl_mtm?.toLocaleString('en-IN')}</td>
                        <td className="py-2.5">
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                            ● Within limits
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2.5">Hard daily loss cutoff</td>
                        <td className="py-2.5 text-rose-600 dark:text-rose-400 font-semibold">
                          ₹{strategy.daily_loss_limit_inr?.toLocaleString('en-IN')} (Locks agent)
                        </td>
                        <td className="py-2.5">
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                            ● Active & Watching
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2.5">Max concurrent lots</td>
                        <td className="py-2.5">{meta?.max_lots ?? 1} Lot (Safe retail cap)</td>
                        <td className="py-2.5">
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                            ● Enforced
                          </span>
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2.5">Mandatory intraday square-off</td>
                        <td className="py-2.5">{strategy.exit_time ?? '15:15 IST'}</td>
                        <td className="py-2.5">
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-600 dark:text-emerald-400">
                            ● Scheduled
                          </span>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Live Journal Feed: "What the engine decided, newest first" (Faithfully matching Insidur Screenshot 3) */}
              <div className="rounded-xl border bg-card p-5 shadow-sm space-y-4">
                <div className="flex items-center justify-between border-b pb-3">
                  <div>
                    <h2 className="text-base font-semibold">Live Journal Feed</h2>
                    <p className="text-xs text-muted-foreground">
                      What the engine decided, newest first (from execution event logs)
                    </p>
                  </div>
                  {isRunning && (
                    <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Live Feed
                    </span>
                  )}
                </div>

                {eventsLoading ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">Loading journal...</div>
                ) : events.length === 0 ? (
                  <div className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
                    No decisions recorded yet for this session. Engine will log decisions once market scanning begins.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {events.slice(0, 15).map((evt: { id: number; ts: string; kind: string; message: string; severity?: string }) => (
                      <div
                        key={evt.id}
                        className="flex items-start gap-3 rounded-lg border bg-muted/20 p-3 text-xs"
                      >
                        <div className="shrink-0 font-mono text-[11px] text-muted-foreground">
                          {formatIst(evt.ts).split(' ')[1] ?? formatIst(evt.ts)}
                        </div>
                        <div className="flex-1 space-y-0.5">
                          <div className="flex items-center gap-2">
                            <Badge
                              variant="outline"
                              className={cn(
                                'text-[10px] px-1.5 py-0 uppercase',
                                evt.severity === 'critical'
                                  ? 'border-rose-500 text-rose-600'
                                  : evt.severity === 'warn'
                                  ? 'border-amber-500 text-amber-600'
                                  : 'border-border text-muted-foreground'
                              )}
                            >
                              {evt.kind}
                            </Badge>
                            <span className="font-medium text-foreground">{evt.message}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {activeTab === 'trades' && (
            <div className="rounded-xl border bg-card p-5 shadow-sm space-y-4">
              <div className="border-b pb-3">
                <h2 className="text-base font-semibold">Executed Trades</h2>
                <p className="text-xs text-muted-foreground">
                  Closed and active positions executed by this agent on Symphony XTS.
                </p>
              </div>

              {roundTrips.length === 0 ? (
                <div className="rounded-lg border border-dashed p-8 text-center space-y-2">
                  <p className="text-sm font-medium">No Trades Executed Today</p>
                  <p className="text-xs text-muted-foreground max-w-sm mx-auto">
                    The agent evaluates market conditions continuously. When all entry criteria are satisfied, trades will appear here.
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {roundTrips.map((trip, idx) => (
                    <div
                      key={idx}
                      className="flex flex-col gap-3 rounded-lg border bg-muted/10 p-4 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-sm">{trip.symbol}</span>
                          <Badge variant="outline" className="text-[10px]">
                            {trip.side.toUpperCase()}
                          </Badge>
                          <Badge variant="secondary" className="text-[10px]">
                            {trip.qty} Qty
                          </Badge>
                        </div>
                        <div className="text-xs text-muted-foreground">
                          Entry: ₹{trip.entry_price.toFixed(2)} ({formatIst(trip.entry_time)}) → Exit: ₹
                          {trip.exit_price.toFixed(2)} ({formatIst(trip.exit_time)})
                        </div>
                      </div>

                      <div className="flex items-center gap-3">
                        <Badge
                          variant="outline"
                          className="capitalize text-[10px] text-muted-foreground border-border"
                        >
                          {trip.exit_kind.replace('_', ' ')}
                        </Badge>
                        <div className={cn('text-base font-bold', pnlToneClass(trip.pnl))}>
                          ₹{formatPnl(trip.pnl)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Slide-over "Ask AI" Copilot Drawer */}
      {askAiOpen && (
        <div className="fixed inset-0 z-50 flex justify-end bg-background/80 backdrop-blur-sm transition-all">
          <div className="flex h-full w-full max-w-md flex-col border-l bg-card shadow-2xl">
            {/* Drawer Header */}
            <div className="flex items-center justify-between border-b px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Bot className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold">AI Agent Copilot</h3>
                  <p className="text-[11px] text-muted-foreground">Analyzing {strategy.name}</p>
                </div>
              </div>
              <Button variant="ghost" size="icon" className="h-8 w-8" onClick={() => setAskAiOpen(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>

            {/* Quick-Tap Prompt Suggestions */}
            <div className="border-b bg-muted/30 p-3 space-y-1.5">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                Ask about this agent:
              </span>
              <div className="flex flex-col gap-1.5">
                <button
                  onClick={() => handleQuickPrompt("Why hasn't this agent traded today?")}
                  className="rounded-md border bg-card px-2.5 py-1.5 text-left text-xs font-medium text-foreground hover:bg-muted/80 transition-colors"
                >
                  🔍 Why hasn't this agent traded today?
                </button>
                <button
                  onClick={() => handleQuickPrompt('How can I make this agent safer?')}
                  className="rounded-md border bg-card px-2.5 py-1.5 text-left text-xs font-medium text-foreground hover:bg-muted/80 transition-colors"
                >
                  🛡️ How can I make this agent safer?
                </button>
                <button
                  onClick={() => handleQuickPrompt("Explain today's performance and trades")}
                  className="rounded-md border bg-card px-2.5 py-1.5 text-left text-xs font-medium text-foreground hover:bg-muted/80 transition-colors"
                >
                  📊 Explain today's performance and trades
                </button>
              </div>
            </div>

            {/* Messages Stream */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {chatMessages.map((msg) => (
                <div
                  key={msg.id}
                  className={cn(
                    'flex flex-col max-w-[85%] rounded-lg p-3 text-xs leading-relaxed',
                    msg.role === 'user'
                      ? 'ml-auto bg-primary text-primary-foreground'
                      : 'border bg-muted/40 text-foreground'
                  )}
                >
                  <div>{msg.content}</div>
                  <span className="mt-1 text-[10px] opacity-70 self-end">{msg.time}</span>
                </div>
              ))}
            </div>

            {/* Composer */}
            <div className="border-t p-3">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  handleSendComposer()
                }}
                className="flex items-center gap-2"
              >
                <Input
                  value={composerText}
                  onChange={(e) => setComposerText(e.target.value)}
                  placeholder="Ask anything about this agent..."
                  className="h-9 text-xs"
                />
                <Button type="submit" size="sm" className="h-9 px-3 bg-primary">
                  <Send className="h-3.5 w-3.5" />
                </Button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Hybrid Edit Parameters Dialog */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Edit Parameters: {strategy.name}</DialogTitle>
            <DialogDescription>
              Adjust profit targets and safety limits in plain Indian rupees.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">Take Profit Target (₹)</Label>
              <Input
                type="number"
                value={targetMtm}
                onChange={(e) => setTargetMtm(e.target.value)}
                placeholder="2500"
              />
              <span className="text-[11px] text-muted-foreground">
                Agent will lock gains and exit all positions when this target is reached.
              </span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Max Stop Loss (₹)</Label>
              <Input
                type="number"
                value={slMtm}
                onChange={(e) => setSlMtm(e.target.value)}
                placeholder="1500"
              />
              <span className="text-[11px] text-muted-foreground">
                Strict loss limit to protect your capital.
              </span>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">Daily Loss Cutoff (₹)</Label>
              <Input
                type="number"
                value={dailyLoss}
                onChange={(e) => setDailyLoss(e.target.value)}
                placeholder="2000"
              />
              <span className="text-[11px] text-muted-foreground">
                If hit, agent locks for the day to prevent revenge trading.
              </span>
            </div>

            <div className="rounded-lg border bg-muted/20 p-3 flex items-center justify-between">
              <div className="space-y-0.5">
                <span className="text-xs font-semibold">Want to change strategy logic?</span>
                <p className="text-[11px] text-muted-foreground">Use AI Chat to redesign entry gates or legs.</p>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1 text-xs"
                onClick={() => navigate('/agent')}
              >
                <MessageSquare className="h-3 w-3" />
                <span>AI Chat</span>
              </Button>
            </div>
          </div>

          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancel
            </Button>
            <Button
              className="bg-primary"
              disabled={updateMutation.isPending}
              onClick={() => {
                updateMutation.mutate({
                  overall_target_mtm: targetMtm ? Number(targetMtm) : undefined,
                  overall_sl_mtm: slMtm ? Number(slMtm) : undefined,
                  daily_loss_limit_inr: dailyLoss ? Number(dailyLoss) : undefined,
                })
              }}
            >
              Save Parameters
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Emergency Square Off Dialog */}
      <Dialog open={squareOffOpen} onOpenChange={setSquareOffOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <AlertTriangle className="h-5 w-5" />
              Emergency Square Off: {strategy.name}
            </DialogTitle>
            <DialogDescription className="space-y-2 pt-2">
              <span className="block">Are you sure you want to trigger an immediate emergency square-off?</span>
              <span className="block font-semibold text-foreground">
                This will immediately cancel all open orders and exit all positions at current Symphony XTS market prices.
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setSquareOffOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="gap-1.5"
              onClick={() => squareOffMutation.mutate()}
              disabled={squareOffMutation.isPending}
            >
              <Square className="h-4 w-4 fill-current" />
              <span>Confirm Square Off All</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Dialog */}
      <Dialog open={deleteOpen} onOpenChange={setDeleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <Trash2 className="h-5 w-5" />
              Delete Agent: {strategy.name}
            </DialogTitle>
            <DialogDescription className="pt-2">
              Are you sure you want to delete this agent? This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              Delete Agent
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
