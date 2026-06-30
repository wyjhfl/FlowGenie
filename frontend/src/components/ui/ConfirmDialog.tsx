// 确认对话框 - 基于 Radix AlertDialog 实现（shadcn 风格），替代原生 confirm()，支持 danger 危险操作样式
import { type ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
} from '@/components/ui/AlertDialog'
import { cn } from '@/lib/utils'

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: ReactNode
  confirmText?: string // 默认"确认"
  cancelText?: string // 默认"取消"
  danger?: boolean // 危险操作（确认按钮红色）
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmText = '确认',
  cancelText = '取消',
  danger = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <AlertDialog open={open} onOpenChange={(next) => { if (!next) onCancel() }}>
      <AlertDialogContent className="max-w-[440px]">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <TriangleAlert
              size={22}
              className={cn(danger ? 'text-destructive' : 'text-primary')}
              aria-hidden="true"
            />
            {title}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="text-sm text-muted-foreground">{message}</div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel
            onClick={onCancel}
            aria-label={cancelText}
          >
            {cancelText}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => {
              // 阻止 Radix 默认关闭，让父组件控制 open 状态切换
              e.preventDefault()
              onConfirm()
            }}
            aria-label={confirmText}
            className={cn(!danger && 'bg-primary text-primary-foreground hover:bg-primary/90')}
          >
            {confirmText}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}
