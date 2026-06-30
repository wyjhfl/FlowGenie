// 徽章组件 - shadcn/ui 风格，用于标签/状态标记
// 颜色映射：default 紫 / secondary 灰 / destructive 红 / outline 透明
// 新增状态色：success 绿 / warning 橙 / info 蓝（半透明底 + 同色字 + 同色边）
import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/lib/utils'

const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        // 半透明紫底 + 紫字 + 紫边
        default: 'border-primary/30 bg-primary/15 text-primary',
        // 灰色：次级底 + 灰字 + 边框（主题自适应）
        secondary: 'border-border bg-secondary text-muted-foreground',
        // 红色：半透明红底 + 红字 + 红边
        destructive: 'border-destructive/30 bg-destructive/15 text-destructive',
        // 透明：仅边框
        outline: 'border-border text-foreground',
        // 绿色（成功状态）
        success: 'border-success/30 bg-success/15 text-success',
        // 橙色（警告状态）
        warning: 'border-warning/30 bg-warning/15 text-warning',
        // 蓝色（信息状态）
        info: 'border-info/30 bg-info/15 text-info',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

const Badge = React.forwardRef<HTMLDivElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <div ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />
  )
)
Badge.displayName = 'Badge'

export { Badge, badgeVariants }
