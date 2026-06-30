// 全局 Toast 通知系统 - 右上角堆叠、自动消失、framer-motion 入场/离场、进度条倒计时
import {
  createContext,
  useContext,
  useState,
  useCallback,
  useRef,
  useEffect,
  type ReactNode,
} from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { CircleCheck, CircleX, TriangleAlert, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'warning' | 'info'

interface ToastItem {
  id: number
  type: ToastType
  message: string
  duration: number
}

interface ToastContextValue {
  show: (message: string, type?: ToastType, duration?: number) => void
  success: (message: string) => void
  error: (message: string) => void
  warning: (message: string) => void
  info: (message: string) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}

// 各类型对应的左侧色条颜色 + 图标（统一使用 HSL token，避免硬编码 hex）
const TYPE_CONFIG: Record<ToastType, { color: string; icon: ReactNode }> = {
  success: { color: 'hsl(var(--success))', icon: <CircleCheck size={18} /> },
  error: { color: 'hsl(var(--destructive))', icon: <CircleX size={18} /> },
  warning: { color: 'hsl(var(--warning))', icon: <TriangleAlert size={18} /> },
  info: { color: 'hsl(var(--primary))', icon: <Info size={18} /> },
}

// 堆叠上限：超过时移除最早的
const MAX_TOASTS = 5

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const idRef = useRef(0)
  // 记录每个 toast 的自动消失定时器，便于卸载/手动关闭时清理
  const timersRef = useRef<Map<number, number>>(new Map())

  // 移除单个 toast：直接从列表剔除，离场动画由 AnimatePresence exit 处理
  const removeToast = useCallback((id: number) => {
    const oldTimer = timersRef.current.get(id)
    if (oldTimer) {
      window.clearTimeout(oldTimer)
      timersRef.current.delete(id)
    }
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const show = useCallback(
    (message: string, type: ToastType = 'info', duration?: number) => {
      const id = ++idRef.current
      // error 默认 5 秒，其余默认 3 秒
      const realDuration = duration ?? (type === 'error' ? 5000 : 3000)
      setToasts((prev) => {
        const next = [...prev, { id, type, message, duration: realDuration }]
        // 超过上限：立即移除最早的队首
        if (next.length > MAX_TOASTS) {
          const removed = next.shift()
          if (removed) {
            const t = timersRef.current.get(removed.id)
            if (t) {
              window.clearTimeout(t)
              timersRef.current.delete(removed.id)
            }
          }
        }
        return next
      })
      // 自动消失
      const autoTimer = window.setTimeout(() => {
        removeToast(id)
      }, realDuration)
      timersRef.current.set(id, autoTimer)
    },
    [removeToast]
  )

  const success = useCallback((m: string) => show(m, 'success'), [show])
  const error = useCallback((m: string) => show(m, 'error'), [show])
  const warning = useCallback((m: string) => show(m, 'warning'), [show])
  const info = useCallback((m: string) => show(m, 'info'), [show])

  // 组件卸载时清理所有未触发的定时器，避免内存泄漏与状态污染
  useEffect(() => {
    return () => {
      timersRef.current.forEach((t) => window.clearTimeout(t))
      timersRef.current.clear()
    }
  }, [])

  const value: ToastContextValue = { show, success, error, warning, info }

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed right-4 top-4 z-[2000] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
        aria-live="polite"
        aria-atomic="false"
      >
        <AnimatePresence>
          {toasts.map((t) => {
            const cfg = TYPE_CONFIG[t.type]
            return (
              <motion.div
                key={t.id}
                layout
                initial={{ opacity: 0, y: -100 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
                className="relative flex items-center gap-3 overflow-hidden rounded-lg border border-border bg-card/95 p-3 pl-4 shadow-lg backdrop-blur-xl"
                role="alert"
              >
                <span
                  className="absolute left-0 top-0 h-full w-1"
                  style={{ background: cfg.color }}
                />
                <span className="flex shrink-0" style={{ color: cfg.color }}>
                  {cfg.icon}
                </span>
                <span className="flex-1 text-sm text-foreground">{t.message}</span>
                <button
                  type="button"
                  className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  aria-label="关闭通知"
                  onClick={() => removeToast(t.id)}
                >
                  <X size={14} />
                </button>
                <span
                  className="toast-progress absolute bottom-0 left-0 h-0.5 w-full"
                  style={{
                    background: cfg.color,
                    animationDuration: `${t.duration}ms`,
                  }}
                />
              </motion.div>
            )
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  )
}
