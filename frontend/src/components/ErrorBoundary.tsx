// 全局错误边界：捕获 React 渲染期错误，展示兜底页（刷新 / 复制错误）
import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { Button } from '@/components/ui/Button'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  // 渲染期抛错时切换为错误态，记录 error 对象
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error }
  }

  // 副作用通道：可在此上报错误日志（这里仅保留钩子，避免外部依赖）
  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 捕获到未处理错误:', error, info)
  }

  // 复制错误堆栈到剪贴板，使用 alert 反馈（class component 无法使用 useToast）
  private handleCopyError = (): void => {
    const { error } = this.state
    const text = error?.stack || error?.message || ''
    navigator.clipboard
      .writeText(text)
      .then(() => alert('已复制'))
      .catch(() => alert('复制失败'))
  }

  render(): ReactNode {
    const { hasError, error } = this.state
    if (!hasError) return this.props.children

    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-background p-6 text-foreground">
        <div className="flex w-full max-w-[600px] flex-col items-center gap-6 text-center">
          <AlertTriangle size={48} className="shrink-0 text-destructive" aria-hidden />

          <h1 className="text-2xl font-semibold">应用发生错误</h1>

          <pre className="max-h-[300px] w-full overflow-auto rounded-md border border-border bg-muted p-4 text-left text-sm whitespace-pre-wrap break-words">
            {error?.message || '未知错误'}
          </pre>

          <div className="flex flex-wrap items-center justify-center gap-3">
            <Button onClick={() => window.location.reload()}>刷新页面</Button>
            <Button variant="outline" onClick={this.handleCopyError}>
              复制错误
            </Button>
          </div>
        </div>
      </div>
    )
  }
}

export default ErrorBoundary
