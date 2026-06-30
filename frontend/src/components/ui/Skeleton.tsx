// 骨架屏组件 - shadcn/ui 风格基础组件 + 业务组合组件
// shimmer 流动光带：linear-gradient(90deg, 0.04→0.08→0.04) + background-size 200% + animate-shimmer
import * as React from 'react'
import { cn } from '@/lib/utils'

/** 基础骨架块：shimmer 流动光带占位 */
function Skeleton({ className, style, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('animate-shimmer rounded-md', className)}
      style={{
        // 三段式渐变：两端 0.04 透明度，中间 0.08 高亮，模拟光带从左滑到右
        // 使用 --foreground 让暗色主题为白光、亮色主题为深光
        background:
          'linear-gradient(90deg, hsl(var(--foreground) / 0.04) 0%, hsl(var(--foreground) / 0.08) 50%, hsl(var(--foreground) / 0.04) 100%)',
        backgroundSize: '200% 100%',
        ...style,
      }}
      {...props}
    />
  )
}

interface SkeletonTextProps {
  lines?: number
  className?: string
}

/** 多行文本骨架：模拟段落或列表描述 */
export function SkeletonText({ lines = 3, className }: SkeletonTextProps) {
  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className="h-2.5" style={{ width: i === lines - 1 ? '60%' : '100%' }} />
      ))}
    </div>
  )
}

/** 数字骨架：用于 Dashboard 统计卡片 */
export function SkeletonNumber() {
  return <Skeleton className="h-7 w-3/5 mt-1" />
}

/** 工作流列表项骨架卡片：模拟标题行 + 描述行 + 操作行布局 */
export function SkeletonCard() {
  return (
    <div className="flex flex-col gap-2 rounded-md border border-border bg-card p-3 px-4">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-3.5 w-[70%]" />
        <Skeleton className="h-2.5 w-[90%]" />
      </div>
      <div className="flex items-center gap-2">
        <Skeleton className="h-3.5 w-3.5 rounded-full" />
        <Skeleton className="h-2.5 w-10" />
      </div>
      <div className="flex gap-2">
        <Skeleton className="h-5 w-5 rounded-sm" />
        <Skeleton className="h-5 w-5 rounded-sm" />
        <Skeleton className="h-5 w-5 rounded-sm" />
      </div>
    </div>
  )
}

/** 工具条骨架：用于 Dashboard 工具使用频率 Top 5 占位 */
export function SkeletonToolBar() {
  return (
    <div className="grid grid-cols-[80px_1fr_30px] items-center gap-3 mb-2">
      <Skeleton className="h-3 w-full" />
      <div className="h-2 rounded-full bg-muted overflow-hidden">
        <Skeleton className="h-full w-3/5 rounded-full" />
      </div>
      <Skeleton className="h-3 w-5" />
    </div>
  )
}

/** 趋势图骨架：用于 Dashboard 7 天趋势占位 */
export function SkeletonTrendChart() {
  return (
    <div className="flex items-end gap-2 h-[120px] py-3">
      {Array.from({ length: 7 }).map((_, i) => (
        <Skeleton
          key={i}
          className="flex-1 min-w-0 rounded-t-sm"
          style={{ height: `${30 + ((i * 13) % 60)}%` }}
        />
      ))}
    </div>
  )
}

export { Skeleton }
