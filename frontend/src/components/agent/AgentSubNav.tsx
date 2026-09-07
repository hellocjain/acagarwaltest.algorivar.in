import { Bot, MessageSquare, SlidersHorizontal } from 'lucide-react'
import { Link, useLocation } from 'react-router'
import { cn } from '@/lib/utils'

export interface AgentSubNavProps {
  className?: string
}

export function AgentSubNav({ className }: AgentSubNavProps) {
  const location = useLocation()
  const pathname = location.pathname

  const navItems = [
    {
      label: 'AI Chat',
      href: '/agent',
      icon: MessageSquare,
      active: pathname === '/agent' || pathname.startsWith('/agent/chat'),
    },
    {
      label: 'My Agents',
      href: '/agent/my-agents',
      icon: Bot,
      active: pathname.startsWith('/agent/my-agents'),
    },
    {
      label: 'Settings',
      href: '/agent/config',
      icon: SlidersHorizontal,
      active: pathname === '/agent/config',
    },
  ]

  return (
    <div className={cn('flex items-center justify-between border-b bg-background/95 px-4 py-2 backdrop-blur', className)}>
      <div className="flex items-center space-x-1">
        {navItems.map((item) => {
          const Icon = item.icon
          return (
            <Link
              key={item.href}
              to={item.href}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-1.5 text-xs font-medium transition-colors',
                item.active
                  ? 'bg-primary/10 text-primary font-semibold'
                  : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
              )}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{item.label}</span>
            </Link>
          )
        })}
      </div>
      <div className="flex items-center gap-2">
        <span className="flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
          AC Agarwal Symphony XTS Active
        </span>
      </div>
    </div>
  )
}
