// pages/agent/AgentCockpit.tsx
// Autonomous Trading Agents Cockpit: command center for all AI trading agents.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  Bot,
  Clock,
  MessageSquare,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Shield,
  Square,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import {
  closeAll,
  listStrategies,
  startRun,
  stopRun,
  strategyQueryKeys,
  useStrategyListPnl,
} from '@/api/strategy_module'
import { AgentSubNav } from '@/components/agent/AgentSubNav'
import { Navbar } from '@/components/layout/Navbar'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { StrategySummary } from '@/types/strategy_module'
import { formatPnl, pnlToneClass } from '@/types/strategy_module'
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
  plain_language?: {
    when?: string
    entry_gates?: string[]
    it_scans?: string
    how_it_exits?: string[]
  }
}

function extractMetadata(strategy: StrategySummary): AgentMetadata | null {
  const scheduler = strategy.scheduler as unknown as Record<string, unknown> | null
  if (!scheduler) return null
  return (scheduler.agent_metadata as AgentMetadata) ?? null
}

export default function AgentCockpit() {
  const queryClient = useQueryClient()
  const [squareOffTarget, setSquareOffTarget] = useState<StrategySummary | null>(null)

  const {
    data: strategies = [],
    isLoading,
    isRefetching,
    refetch,
  } = useQuery({
    queryKey: strategyQueryKeys.strategies(),
    queryFn: () => listStrategies({}),
    refetchInterval: 10_000,
  })

  const pnlById = useStrategyListPnl(strategies)

  // Calculate aggregated today metrics
  const { totalPnl, runningCount, pausedCount } = useMemo(() => {
    let total = 0
    let running = 0
    let paused = 0

    for (const s of strategies) {
      const pnl = pnlById.get(s.id)?.total ?? s.last_finalized_run?.pnl_realized ?? 0
      total += pnl

      if (s.status === 'running') running++
      else if (s.status === 'paused') paused++
    }
    return { totalPnl: total, runningCount: running, pausedCount: paused }
  }, [strategies, pnlById])

  // Pause mutation
  const pauseMutation = useMutation({
    mutationFn: (id: number) => stopRun(id),
    onSuccess: () => {
      showToast.success('Agent paused successfully')
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategies() })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Failed to pause agent')
    },
  })

  // Resume/Deploy mutation (sandbox mode for safety)
  const resumeMutation = useMutation({
    mutationFn: (id: number) => startRun(id, 'sandbox'),
    onSuccess: () => {
      showToast.success('Agent activated in Practice Mode (Sandbox)')
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategies() })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Failed to activate agent')
    },
  })

  // Emergency square off mutation
  const squareOffMutation = useMutation({
    mutationFn: (id: number) => closeAll(id),
    onSuccess: () => {
      showToast.success('All positions squared off successfully')
      setSquareOffTarget(null)
      void queryClient.invalidateQueries({ queryKey: strategyQueryKeys.strategies() })
    },
    onError: (err: Error) => {
      showToast.error(err.message || 'Emergency square off failed')
    },
  })

  return (
    <>
      <Navbar fluid />
      <AgentSubNav />

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-muted/20">
        <div className="mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6">
          {/* Header Banner */}
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h1 className="text-2xl font-bold tracking-tight">My Trading Agents</h1>
                <Badge variant="outline" className="text-xs">
                  {strategies.length} Total
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Autonomous AI agents monitoring Symphony XTS and executing risk-managed strategies.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-2.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => void refetch()}
                disabled={isRefetching}
                className="gap-1.5"
              >
                <RefreshCw className={cn('h-3.5 w-3.5', isRefetching && 'animate-spin')} />
                <span>Refresh</span>
              </Button>
              <Button asChild size="sm" className="gap-1.5 bg-primary font-medium">
                <Link to="/agent">
                  <MessageSquare className="h-4 w-4" />
                  <span>Build with AI Chat</span>
                </Link>
              </Button>
            </div>
          </div>

          {/* Portfolio KPI Summary Strip */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Card className="border-border/60 bg-card/80 backdrop-blur">
              <CardContent className="p-4">
                <div className="text-xs font-medium text-muted-foreground">Today's Realized P&L</div>
                <div className={cn('mt-1 text-2xl font-bold tracking-tight', pnlToneClass(totalPnl))}>
                  ₹{formatPnl(totalPnl)}
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">Across all active agents</div>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-card/80 backdrop-blur">
              <CardContent className="p-4">
                <div className="text-xs font-medium text-muted-foreground">Active & Watching</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-bold tracking-tight text-emerald-600 dark:text-emerald-400">
                    {runningCount}
                  </span>
                  <span className="text-xs text-muted-foreground">agents</span>
                </div>
                <div className="mt-1 flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  Live market scanning
                </div>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-card/80 backdrop-blur">
              <CardContent className="p-4">
                <div className="text-xs font-medium text-muted-foreground">Paused / Idle</div>
                <div className="mt-1 flex items-baseline gap-2">
                  <span className="text-2xl font-bold tracking-tight text-muted-foreground">
                    {pausedCount}
                  </span>
                  <span className="text-xs text-muted-foreground">agents</span>
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">Ready to deploy</div>
              </CardContent>
            </Card>

            <Card className="border-border/60 bg-card/80 backdrop-blur">
              <CardContent className="p-4">
                <div className="text-xs font-medium text-muted-foreground">Safety Protection</div>
                <div className="mt-1 text-2xl font-bold tracking-tight text-primary">
                  100%
                </div>
                <div className="mt-1 flex items-center gap-1 text-[11px] text-muted-foreground">
                  <Shield className="h-3 w-3 text-emerald-500" />
                  SL + Daily loss limits active
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Agent Cards Grid or Empty State */}
          {isLoading ? (
            <div className="flex h-64 items-center justify-center rounded-xl border border-dashed bg-card/50">
              <div className="flex flex-col items-center gap-2">
                <RefreshCw className="h-6 w-6 animate-spin text-muted-foreground" />
                <span className="text-sm text-muted-foreground">Loading your agents...</span>
              </div>
            </div>
          ) : strategies.length === 0 ? (
            <Card className="border-dashed bg-card/50 p-12 text-center">
              <CardContent className="flex flex-col items-center justify-center space-y-4">
                <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                  <Bot className="h-8 w-8" />
                </div>
                <div className="max-w-md space-y-1">
                  <h3 className="text-lg font-semibold tracking-tight">No Trading Agents Yet</h3>
                  <p className="text-sm text-muted-foreground">
                    Tell our AI what kind of strategy you want in plain everyday English. It will configure safe entry gates, strict stop-losses, and automated profit exits.
                  </p>
                </div>
                <Button asChild className="gap-2 bg-primary">
                  <Link to="/agent">
                    <Plus className="h-4 w-4" />
                    <span>Create Your First Agent</span>
                  </Link>
                </Button>
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-5 md:grid-cols-2 lg:grid-cols-3">
              {strategies.map((strategy) => {
                const meta = extractMetadata(strategy)
                const pnl = pnlById.get(strategy.id)?.total ?? strategy.last_finalized_run?.pnl_realized ?? 0
                const isRunning = strategy.status === 'running'
                const isPaused = strategy.status === 'paused'

                return (
                  <Card
                    key={strategy.id}
                    className={cn(
                      'group relative flex flex-col justify-between overflow-hidden transition-all duration-200 hover:shadow-md',
                      isRunning && 'border-emerald-500/40 shadow-sm'
                    )}
                  >
                    <CardHeader className="pb-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="space-y-1">
                          <CardTitle className="text-base font-semibold leading-tight group-hover:text-primary transition-colors">
                            <Link to={`/agent/my-agents/${strategy.id}`}>{strategy.name}</Link>
                          </CardTitle>
                          <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                            {meta?.universe || strategy.strategy_kind === 'scanner' ? (
                              <>
                                <Badge variant="secondary" className="bg-purple-500/10 text-purple-600 dark:text-purple-400 px-1.5 py-0 text-[10px] font-semibold">
                                  {meta?.instrument_preference === 'options'
                                    ? `${meta?.universe || 'F&O'} Stock Options`
                                    : meta?.instrument_preference === 'futures'
                                    ? `${meta?.universe || 'F&O'} Stock Futures`
                                    : `${meta?.universe || 'NIFTY 500'} Scanner`}
                                </Badge>
                                {meta?.instrument_preference === 'options' && (
                                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/5 text-amber-600 dark:text-amber-400 px-1.5 py-0 text-[10px]">
                                    Rollover Shield
                                  </Badge>
                                )}
                              </>
                            ) : (
                              <Badge variant="secondary" className="px-1.5 py-0 text-[10px] font-semibold">
                                {strategy.underlying}
                              </Badge>
                            )}
                            {meta?.category && (
                              <Badge variant="outline" className="px-1.5 py-0 text-[10px] capitalize">
                                {meta.category.replace('_', ' ')}
                              </Badge>
                            )}
                            <Badge
                              variant="outline"
                              className="border-blue-500/30 bg-blue-500/5 text-blue-600 dark:text-blue-400 px-1.5 py-0 text-[10px]"
                            >
                              Practice Mode
                            </Badge>
                          </div>
                        </div>

                        {/* Traffic Light Status Badge */}
                        <div className="shrink-0">
                          {isRunning ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                              <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                              {strategy.strategy_kind === 'scanner' || meta?.universe ? 'Scanning' : 'Watching'}
                            </span>
                          ) : isPaused ? (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-2.5 py-1 text-xs font-semibold text-amber-600 dark:text-amber-400">
                              <Pause className="h-3 w-3" />
                              Paused
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 rounded-full bg-muted px-2.5 py-1 text-xs font-medium text-muted-foreground">
                              <span className="h-2 w-2 rounded-full bg-muted-foreground/50" />
                              Stopped
                            </span>
                          )}
                        </div>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-4 pb-4">
                      {/* Large Rupee P&L Display */}
                      <div className="rounded-lg border bg-background/50 p-3">
                        <div className="flex items-baseline justify-between">
                          <span className="text-xs font-medium text-muted-foreground">Today's P&L</span>
                          <span className={cn('text-lg font-bold tracking-tight', pnlToneClass(pnl))}>
                            ₹{formatPnl(pnl)}
                          </span>
                        </div>

                        {/* Risk & Safety Limits */}
                        {meta?.instrument_preference === 'options' ? (
                          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t pt-2 text-[11px] text-muted-foreground">
                            <div>
                              <span>Prem Budget: </span>
                              <span className="font-semibold text-foreground">
                                ₹{(meta?.max_premium_per_trade_inr ?? meta?.capital_per_trade_inr ?? 15000).toLocaleString('en-IN')}
                              </span>
                            </div>
                            <div className="text-right">
                              <span>Max Contracts: </span>
                              <span className="font-semibold text-foreground">
                                {meta?.max_concurrent_positions ?? 3} Concurrent
                              </span>
                            </div>
                          </div>
                        ) : strategy.strategy_kind === 'scanner' || meta?.universe ? (
                          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t pt-2 text-[11px] text-muted-foreground">
                            <div>
                              <span>Alloc / Trade: </span>
                              <span className="font-semibold text-foreground">
                                ₹{(meta?.capital_per_trade_inr ?? 10000).toLocaleString('en-IN')}
                              </span>
                            </div>
                            <div className="text-right">
                              <span>Max Stocks: </span>
                              <span className="font-semibold text-foreground">
                                {meta?.max_concurrent_positions ?? 5} Concurrent
                              </span>
                            </div>
                          </div>
                        ) : (
                          <div className="mt-2.5 grid grid-cols-2 gap-2 border-t pt-2 text-[11px] text-muted-foreground">
                            <div>
                              <span>Max Daily Loss: </span>
                              <span className="font-semibold text-foreground">
                                ₹{(strategy.daily_loss_limit_inr ?? 0).toLocaleString('en-IN')}
                              </span>
                            </div>
                            <div className="text-right">
                              <span>Max Lots: </span>
                              <span className="font-semibold text-foreground">
                                {meta?.max_lots ?? 1} Lot
                              </span>
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Plain Language Summary */}
                      <div className="space-y-1.5 text-xs text-muted-foreground">
                        <div className="flex items-center gap-1.5">
                          <Clock className="h-3.5 w-3.5 text-primary shrink-0" />
                          <span className="truncate">
                            {meta?.plain_language?.when ??
                              `Entry: ${strategy.entry_time ?? 'Market open'} · Exit: ${strategy.exit_time ?? '15:15'}`}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <Shield className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                          <span className="truncate">
                            Target: +₹{strategy.overall_target_mtm?.toLocaleString('en-IN') ?? '0'} | SL: -₹
                            {strategy.overall_sl_mtm?.toLocaleString('en-IN') ?? '0'}
                          </span>
                        </div>
                      </div>
                    </CardContent>

                    <CardFooter className="flex flex-col gap-2 border-t bg-muted/10 p-3 pt-3">
                      <div className="flex w-full items-center justify-between gap-2">
                        {isRunning ? (
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1 gap-1.5 border-amber-500/30 text-amber-600 hover:bg-amber-500/10 dark:text-amber-400"
                            onClick={() => pauseMutation.mutate(strategy.id)}
                            disabled={pauseMutation.isPending}
                          >
                            <Pause className="h-3.5 w-3.5" />
                            <span>Pause</span>
                          </Button>
                        ) : (
                          <Button
                            variant="outline"
                            size="sm"
                            className="flex-1 gap-1.5 border-emerald-500/30 text-emerald-600 hover:bg-emerald-500/10 dark:text-emerald-400"
                            onClick={() => resumeMutation.mutate(strategy.id)}
                            disabled={resumeMutation.isPending}
                          >
                            <Play className="h-3.5 w-3.5" />
                            <span>Resume</span>
                          </Button>
                        )}

                        {isRunning && (
                          <Button
                            variant="outline"
                            size="sm"
                            className="gap-1 border-rose-500/30 text-rose-600 hover:bg-rose-500/10 dark:text-rose-400"
                            title="Emergency Square Off"
                            onClick={() => setSquareOffTarget(strategy)}
                          >
                            <Square className="h-3.5 w-3.5 fill-current" />
                            <span>Square Off</span>
                          </Button>
                        )}

                        <Button
                          asChild
                          variant="secondary"
                          size="sm"
                          className="gap-1 font-medium"
                        >
                          <Link to={`/agent/my-agents/${strategy.id}`}>
                            <span>Details</span>
                            <ArrowRight className="h-3.5 w-3.5" />
                          </Link>
                        </Button>
                      </div>
                    </CardFooter>
                  </Card>
                )
              })}
            </div>
          )}
        </div>
      </div>

      {/* Emergency Square Off Confirmation Dialog */}
      <Dialog open={!!squareOffTarget} onOpenChange={(open) => !open && setSquareOffTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-rose-600">
              <AlertTriangle className="h-5 w-5" />
              Emergency Square Off: {squareOffTarget?.name}
            </DialogTitle>
            <DialogDescription className="space-y-2 pt-2">
              <span className="block">
                Are you sure you want to trigger an immediate emergency square-off for this agent?
              </span>
              <span className="block font-semibold text-foreground">
                This will immediately cancel all open limit orders and submit MARKET exit orders to close all positions at current Symphony XTS market price.
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2">
            <Button variant="outline" onClick={() => setSquareOffTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              className="gap-1.5"
              onClick={() => squareOffTarget && squareOffMutation.mutate(squareOffTarget.id)}
              disabled={squareOffMutation.isPending}
            >
              <Square className="h-4 w-4 fill-current" />
              <span>Confirm Square Off All</span>
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
