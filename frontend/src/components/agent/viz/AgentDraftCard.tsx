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
    underlying: string
    strategy_type: string
    capital_inr: number
    stop_loss_inr: number
    target_profit_inr: number
    max_lots: number
    account?: string
    summary?: string
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
          {spec.summary || `${spec.underlying} current_weekly | ${spec.max_lots} lot | SL: ₹${spec.stop_loss_inr} | TGT: ₹${spec.target_profit_inr}`}
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
      {detailsExpanded && spec.plain_language && (
        <div className="mt-3 space-y-2 rounded-lg border border-border/80 bg-muted/30 p-3 text-xs">
          <div className="flex items-start gap-2">
            <ShieldCheck className="mt-0.5 h-3.5 w-3.5 text-primary shrink-0" />
            <div className="space-y-1">
              <span className="font-semibold text-foreground">WHEN: </span>
              <span className="text-muted-foreground">{spec.plain_language.when}</span>
            </div>
          </div>

          {spec.plain_language.it_scans && (
            <div className="pl-5 text-muted-foreground">
              <span className="font-semibold text-foreground">IT SCANS: </span>
              {spec.plain_language.it_scans}
            </div>
          )}

          {spec.plain_language.how_it_exits && spec.plain_language.how_it_exits.length > 0 && (
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
