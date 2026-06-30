// 空状态组件 - 居中布局，图标 + 标题 + 副标题 + 可选 CTA
import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'

interface EmptyStateProps {
  icon?: ReactNode      // SVG 插画或 lucide 图标，缺省用 Inbox
  title: string          // 标题
  description?: string   // 副标题
  action?: ReactNode     // CTA 按钮
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div
      className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center"
      role="status"
    >
      <div className="text-muted-foreground">{icon ?? <Inbox size={24} />}</div>
      <div className="text-base font-semibold text-foreground">{title}</div>
      {description && (
        <div className="text-sm text-muted-foreground">{description}</div>
      )}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
