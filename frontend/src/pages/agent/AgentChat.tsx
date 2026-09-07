/**
 * The agent conversation view.
 *
 * A scrolling thread with the composer pinned under it, the model picker and
 * the conversation's running cost in the header.
 *
 * Four behaviours are worth stating because the obvious implementations of
 * them are wrong:
 *
 * - **Auto-scroll fires on a new turn, not on a new token**, which is
 *   `usePinNewestQuestion`, shared with the chart panel. The trailing spacer
 *   below the thread is this page's half of that bargain: it is what lets the
 *   last question reach the top even when the answer is one line.
 *
 * - **Stop is a server-side action.** `stop()` aborts the fetch for an
 *   immediate end in the browser and posts the cancel route, because a run that
 *   is merely unwatched is still running and still being billed.
 *
 * - **The height comes from the viewport, not from a `calc()`.** The page sits
 *   under `FullWidthLayout`, which is an `h-screen` flex column with
 *   `overflow-hidden`, so this view is one `flex-1 min-h-0` row and every
 *   region inside it either shrinks to its content or takes the remainder.
 *   Exactly one element scrolls, the thread. A `min-height` guess drifts the
 *   moment the header or the composer changes height, and the composer walking
 *   off the bottom of a phone is how that drift shows up.
 *
 * - **The header total is the conversation's, not the session's.** A thread
 *   opened from the sidebar arrives with each stored turn's usage already on
 *   it, so the same sum covers turns typed an hour ago and turns typed a minute
 *   ago. A total that only counted what streamed since the page loaded would
 *   quietly report a long conversation as cheap.
 *
 * Full width is for the chrome, not for the prose. The header spans the
 * viewport and the conversation column does not: a 2000px line length is
 * unreadable, so messages and the composer share one capped, centred column
 * while the sidebar and the header bar use the space around it.
 *
 * The turn's model is resolved before the first stream byte, so switching the
 * picker mid-conversation applies to the next turn and never disturbs the one
 * in flight.
 */

import { useQuery } from '@tanstack/react-query'
import { AlertCircle, Bot, SlidersHorizontal, Zap } from 'lucide-react'
import { useCallback, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router'
import {
  agentErrorMessage,
  agentQueryKeys,
  getSettings,
  type ReasoningEffort,
  truncateConversation,
} from '@/api/agent'
import { startRun } from '@/api/strategy_module'
import { Composer, type ComposerTurn } from '@/components/agent/Composer'
import { ConversationSidebar } from '@/components/agent/ConversationSidebar'
import { Message } from '@/components/agent/Message'
import { ModelPicker } from '@/components/agent/ModelPicker'
import { ConversationUsageBadge, sumUsage } from '@/components/agent/UsageBadge'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { type AgentMessage, useAgentStream } from '@/lib/agent/useAgentStream'
import { usePinNewestQuestion } from '@/lib/agent/useThreadScroll'
import { cn } from '@/lib/utils'

const STARTER_PROMPTS = [
  {
    icon: '🛡️',
    title: 'Safe Weekly Income',
    desc: 'Conservative NIFTY option selling (~₹50k capital, ₹1,500 SL)',
    prompt:
      'Help me set up a safe weekly income strategy on NIFTY with ₹50,000 capital and strict ₹1,500 stop loss protection.',
  },
  {
    icon: '⚡',
    title: 'Expiry Day Momentum',
    desc: 'Small target intraday momentum with ₹1,000 max risk',
    prompt:
      'Create an expiry day momentum strategy on NIFTY with ₹1,000 max stop loss and ₹2,000 profit target.',
  },
  {
    icon: '📉',
    title: 'Nifty Dip Buyer',
    desc: 'Buys 1 lot CE when Nifty touches 20-EMA support',
    prompt:
      'Create a Nifty dip-buying strategy using 20 EMA on 5-minute candles with 1 lot and ₹1,500 stop loss.',
  },
  {
    icon: '🎯',
    title: 'Recommend for my Capital',
    desc: 'AI recommends the safest setup for ₹50,000',
    prompt:
      'I have ₹50,000 capital. Recommend the safest automated trading strategy for steady returns with low drawdown.',
  },
]

/**
 * The reading column shared by the thread and the composer.
 *
 * They must be the same width or the box you type into stops lining up with
 * the answers it produces.
 */
const COLUMN = 'mx-auto w-full max-w-3xl'

export default function AgentChat() {
  const navigate = useNavigate()
  const [modelId, setModelId] = useState<number | null>(null)
  // Per turn, not persisted: effort belongs to the question being asked.
  const [effort, setEffort] = useState<ReasoningEffort>('off')
  const [editError, setEditError] = useState<string | null>(null)

  // The trading switch lives on the config page; the chat only reads it.
  const settings = useQuery({
    queryKey: agentQueryKeys.settings(),
    queryFn: getSettings,
    staleTime: 30_000,
  })
  const { messages, running, error, conversationId, send, stop, confirm, reset, setConversation } =
    useAgentStream({
      surface: 'chat',
      modelId,
      reasoningEffort: effort === 'off' ? null : effort,
      // Asking is not the same as getting: the backend ANDs this with the
      // operator's own trading setting, so a session that asks while trading is
      // off still receives no order tools. Reading it from settings is what
      // makes the config switch actually reach a turn; before this the flag was
      // never set and the order tools could not be offered at all, so an order
      // request came back as a refusal rather than an approval prompt.
      tradingEnabled: settings.data?.data.trading_enabled ?? false,
    })

  const threadRef = useRef<HTMLDivElement>(null)

  const totals = useMemo(() => sumUsage(messages.map((message) => message.usage)), [messages])

  usePinNewestQuestion(threadRef, messages)

  const draftAgents = useMemo(() => {
    const drafts: Array<Record<string, any>> = []
    const seen = new Set<number>()
    for (const msg of messages) {
      if (msg.viz) {
        for (const v of msg.viz) {
          const spec = v.spec as Record<string, any> | undefined
          if (v.kind === 'agent_draft' && spec && typeof spec.strategy_id === 'number') {
            if (!seen.has(spec.strategy_id)) {
              seen.add(spec.strategy_id)
              drafts.push(spec)
            }
          }
        }
      }
    }
    return drafts
  }, [messages])

  const [deployingId, setDeployingId] = useState<number | null>(null)
  const handleDeployDraft = useCallback(async (strategyId: number) => {
    try {
      setDeployingId(strategyId)
      await startRun(strategyId, 'sandbox')
    } catch (err) {
      console.error('Failed to deploy draft:', err)
    } finally {
      setDeployingId(null)
    }
  }, [])

  /**
   * The web-search switch as the last sent turn had it.
   *
   * The composer owns that switch, so a retry or an edit, which do not go
   * through the composer, would otherwise silently re-enable search on a
   * conversation the operator had turned it off for.
   */
  const lastWebSearch = useRef(true)

  const handleSend = useCallback(
    (text: string, turn: ComposerTurn) => {
      lastWebSearch.current = turn.webSearch
      void send(text, turn)
    },
    [send]
  )

  const handleStop = useCallback(() => {
    void stop()
  }, [stop])

  const handleConfirm = useCallback(
    (decisions: Record<string, boolean>) => {
      void confirm(decisions)
    },
    [confirm]
  )

  // The sidebar has already fetched the conversation and hydrated it, so the
  // thread is switched in one commit: the id the next message continues, and
  // the stored turns with their tools, notices and usage on them.
  /** The newest answer, the only one worth offering a retry on. */
  const lastAssistantId = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'assistant') return messages[index].id
    }
    return null
  }, [messages])

  /** The most recent question, which is what a retry replaces. */
  const lastUserMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      if (messages[index].role === 'user') return messages[index]
    }
    return null
  }, [messages])

  /**
   * Replace a question and discard everything after it.
   *
   * The truncation happens on the SERVER first and the local state is rebuilt
   * from what it removed. Splicing locally and letting the server catch up
   * would look identical and be wrong: agno keeps its own copy of the
   * conversation, and a purely local edit leaves the model still answering the
   * question that was just rewritten.
   *
   * A message with no numeric id has never been stored, which happens when a
   * turn is still in flight. There is nothing to truncate, so it is refused
   * rather than silently sending a second question into the same thread.
   */
  const handleEdit = useCallback(
    (messageId: string, text: string) => {
      // Message ids are `stored-<row>` once the server has told us the row, and
      // a local counter like `user-3` before that. Only the first can be
      // truncated, because truncation names rows by database id.
      const match = /^stored-(\d+)$/.exec(messageId)
      const numericId = match ? Number(match[1]) : Number.NaN
      if (!conversationId || !Number.isFinite(numericId)) {
        // Never a silent return. An edit that quietly reverts is exactly what
        // this looked like before the id was carried back from the server.
        setEditError('That message cannot be edited yet. Wait for the turn to finish, then retry.')
        return
      }
      setEditError(null)
      void truncateConversation(conversationId, numericId)
        .then(() => {
          setConversation(
            conversationId,
            messages.slice(
              0,
              messages.findIndex((item) => item.id === messageId)
            )
          )
          send(text, { webSearch: lastWebSearch.current })
        })
        .catch((cause) => {
          // The answer is still on screen and the question unchanged, which is
          // the right place to fail: nothing has been half-removed.
          setEditError(agentErrorMessage(cause, 'Could not edit that message'))
        })
    },
    [conversationId, messages, send, setConversation]
  )

  /**
   * Answer the last question again, after a failure or an unsatisfying answer.
   *
   * This is an edit that changes nothing, so it goes through `handleEdit`
   * rather than beside it. Sending the text again on its own looked right and
   * was not: it appended a second copy of the question and a second answer, so
   * one retry left the thread holding the same question twice, and agno was
   * still carrying the answer the operator had just rejected. Replacing the
   * question with itself removes the old answer on the server first, which is
   * what "try again" means.
   */
  const handleRetry = useCallback(() => {
    if (!lastUserMessage) return
    handleEdit(lastUserMessage.id, lastUserMessage.content)
  }, [handleEdit, lastUserMessage])

  const handleSelectConversation = useCallback(
    (id: number, loaded: AgentMessage[]) => {
      setConversation(id, loaded)
    },
    [setConversation]
  )

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
      {/* The sidebar owns its own width and its own right border; the column
          beside it is min-w-0 so a wide tool result shrinks the thread rather
          than pushing the page sideways. */}
      <ConversationSidebar
        activeId={conversationId}
        surface="chat"
        busy={running}
        onNewChat={reset}
        onSelect={handleSelectConversation}
      />

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        {/* Chrome spans the surface. Only the reading column is capped. */}
        <header className="flex shrink-0 items-center gap-3 border-b border-border px-4 py-2.5">
          <h1 className="text-base font-semibold tracking-tight">Agent</h1>
          <div className="ml-auto flex min-w-0 items-center gap-3">
            {/* What the whole conversation has cost, hydrated turns included.
                New chat lives in the sidebar, which is the one place a thread
                is started, opened or deleted. */}
            {totals.turns > 0 && (
              <div className="hidden items-center gap-1.5 sm:flex">
                <span className="text-[11px] leading-none tracking-wide text-muted-foreground uppercase">
                  Total
                </span>
                <ConversationUsageBadge totals={totals} />
              </div>
            )}
            {/* The only route from the conversation to its own settings. The
                profile menu carries one too, but an operator who is looking at
                the chat does not think to open a dropdown three regions away,
                and the setup screen that used to offer this link is exactly the
                screen a configured instance never sees again. It sits beside
                the model picker because adding a model is what the config page
                is most often opened to do. */}
            <Button
              asChild
              variant="ghost"
              size="icon"
              className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
            >
              <Link to="/agent/config" aria-label="Agent settings">
                <SlidersHorizontal className="h-4 w-4" aria-hidden />
              </Link>
            </Button>
          </div>
        </header>

        {/* The one scrolling element on the page. overflow-x-hidden is the
            backstop: a message that cannot break scrolls inside its own
            container rather than widening the body. */}
        <div ref={threadRef} className="relative min-h-0 flex-1 overflow-x-hidden overflow-y-auto">
          {messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-6 px-6 py-8 text-center max-w-2xl mx-auto">
              <div className="flex flex-col items-center gap-2">
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary/10 text-primary shadow-xs">
                  <Bot className="h-6 w-6" aria-hidden />
                </div>
                <h2 className="text-base font-semibold tracking-tight text-foreground sm:text-lg">
                  Namaste! I am your AC Agarwal Trading Assistant
                </h2>
                <p className="max-w-md text-xs sm:text-sm leading-relaxed text-muted-foreground">
                  I help you build, test, and run automated trading strategies with strict safety nets.
                  Tap a starter option below or describe what you want in simple words.
                </p>
              </div>

              <div className="grid w-full grid-cols-1 gap-2.5 sm:grid-cols-2 text-left">
                {STARTER_PROMPTS.map((item, idx) => (
                  <button
                    key={idx}
                    type="button"
                    onClick={() => handleSend(item.prompt, { webSearch: false, attachments: [] })}
                    className="group flex flex-col justify-between rounded-xl border border-border bg-card p-3 transition-all hover:border-primary/50 hover:bg-muted/40 hover:shadow-xs cursor-pointer text-left"
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-base">{item.icon}</span>
                      <span className="text-xs font-semibold text-foreground group-hover:text-primary transition-colors">
                        {item.title}
                      </span>
                    </div>
                    <p className="text-[11px] leading-normal text-muted-foreground">
                      {item.desc}
                    </p>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={cn(COLUMN, 'space-y-6 px-4 py-4')}>
              {messages.map((message) => (
                <Message
                  key={message.id}
                  message={message}
                  onConfirm={handleConfirm}
                  onEdit={message.role === 'user' ? handleEdit : undefined}
                  onRetry={
                    message.role === 'assistant' && message.id === lastAssistantId
                      ? handleRetry
                      : undefined
                  }
                  busy={running}
                />
              ))}
              {/* Lets the newest question reach the top of the viewport even
                  when the answer under it is only a line long. */}
              <div className="h-[40vh]" aria-hidden />
            </div>
          )}
        </div>

        <div className="shrink-0 border-t border-border">
          <div className={cn(COLUMN, 'space-y-2 px-4 py-3')}>
            {(error || editError) && (
              <Alert variant="destructive" className="py-2">
                <AlertCircle className="h-4 w-4" aria-hidden />
                <AlertDescription className="text-xs">{error || editError}</AlertDescription>
              </Alert>
            )}
            <ConversationUsageBadge totals={totals} className="px-1 sm:hidden" />
            <Composer
              onSend={handleSend}
              onStop={handleStop}
              running={running}
              // The same row the picker is showing, so the attach control and
              // the turn agree about which model has to read the file.
              modelId={modelId}
              controls={
                <ModelPicker
                  value={modelId}
                  onChange={setModelId}
                  effort={effort}
                  onEffortChange={setEffort}
                  disabled={running}
                />
              }
            />
          </div>
        </div>
      </div>

      {/* Right Rail (Insidur-Style Drafts Rail) */}
      {draftAgents.length > 0 && (
        <aside className="hidden w-80 shrink-0 flex-col border-l border-border bg-muted/10 p-4 xl:flex overflow-y-auto">
          <div className="flex items-center justify-between border-b border-border pb-3">
            <span className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">
              In This Chat
            </span>
            <span className="rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-semibold text-primary">
              {draftAgents.length} {draftAgents.length === 1 ? 'Agent' : 'Agents'}
            </span>
          </div>

          <div className="mt-3 space-y-3">
            <span className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Drafts
            </span>
            {draftAgents.map((draft, idx) => (
              <div
                key={idx}
                className="rounded-xl border border-border bg-card p-3.5 shadow-xs transition-all hover:border-primary/40"
              >
                <div className="mb-1.5 flex items-center gap-2">
                  <Zap className="h-3.5 w-3.5 text-primary" />
                  <h5 className="truncate text-xs font-semibold text-foreground">{draft.name}</h5>
                </div>
                <p className="mb-3 line-clamp-2 font-mono text-[11px] text-muted-foreground">
                  {draft.summary || `${draft.underlying} | ${draft.max_lots} lot | SL: ₹${draft.stop_loss_inr}`}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    className="h-7 flex-1 text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90"
                    disabled={deployingId === draft.strategy_id}
                    onClick={() => handleDeployDraft(draft.strategy_id)}
                  >
                    {deployingId === draft.strategy_id ? 'Deploying…' : 'Deploy'}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    className="h-7 flex-1 text-xs"
                    onClick={() => navigate(`/agent/my-agents/${draft.strategy_id}`)}
                  >
                    Review
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </aside>
      )}
    </div>
  )
}
