// 顶部命令栏 - 48px 高，面包屑 + 内嵌需求输入框 + 操作按钮
import { useState, useRef, useEffect } from 'react'
import { ChevronRight, RefreshCw, Save, Sparkles, Loader2 } from 'lucide-react'
import { motion } from 'framer-motion'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/Tooltip'
import { cn } from '@/lib/utils'

export interface CommandBarProps {
  workflowName: string | null
  onOpenCommand: () => void // 唤起 ⌘K 命令面板
  onRefresh: () => void
  onSave: () => void
  saving: boolean
  onParse?: (requirement: string) => void
  loading?: boolean
  refineMode?: boolean
  viewName?: string // 当前视图名（仪表盘/模板库），非空时面包屑显示此值
  actionsDisabled?: boolean // 非 editor 视图时禁用刷新/保存按钮
}

export function CommandBar({
  workflowName,
  onRefresh,
  onSave,
  saving,
  onParse,
  loading = false,
  refineMode = false,
  viewName,
  actionsDisabled = false,
}: CommandBarProps) {
  const [expanded, setExpanded] = useState(false)
  const [requirement, setRequirement] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // 展开浮层时自动聚焦 Textarea
  useEffect(() => {
    if (expanded && textareaRef.current) {
      textareaRef.current.focus()
    }
  }, [expanded])

  // Esc 关闭浮层 + 点击外部关闭
  useEffect(() => {
    if (!expanded) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        setExpanded(false)
      }
    }
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node
      if (
        overlayRef.current &&
        !overlayRef.current.contains(target) &&
        inputRef.current &&
        !inputRef.current.contains(target)
      ) {
        setExpanded(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [expanded])

  const handleSubmit = () => {
    const trimmed = requirement.trim()
    if (!trimmed || !onParse) return
    onParse(trimmed)
    setRequirement('')
    setExpanded(false)
  }

  const handleExpand = () => {
    setExpanded(true)
  }

  return (
    <TooltipProvider delayDuration={300}>
      <header className="relative z-50 flex h-12 shrink-0 items-center border-b border-border bg-background/80 backdrop-blur-xl">
        {/* 左面包屑 */}
        <div className="flex items-center gap-2 px-4">
          <span className="text-sm text-muted-foreground">FlowGenie</span>
          <ChevronRight className="h-4 w-4 text-muted-foreground/70" />
          <span className="text-sm font-medium text-foreground">
            {viewName ?? workflowName ?? '未命名'}
          </span>
        </div>

        {/* 中部内嵌需求输入框：点击/聚焦展开多行 Textarea 浮层 */}
        <div className="relative mx-auto w-full max-w-2xl flex-1">
          <Input
            ref={inputRef}
            type="text"
            readOnly
            value=""
            data-command-bar-input
            placeholder={
              refineMode
                ? '描述调整指令，AI 优化工作流... (⌘K)'
                : '描述需求，AI 生成工作流... (⌘K)'
            }
            onFocus={handleExpand}
            onClick={handleExpand}
            className="h-8 cursor-text bg-secondary border border-border focus-visible:border-primary/60 transition-colors duration-150"
          />
          {expanded && (
            <motion.div
              ref={overlayRef}
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ type: 'spring', stiffness: 300, damping: 25 }}
              className="absolute left-0 top-full z-50 mt-2 w-[480px] max-w-[90vw] rounded-lg border border-border bg-card/95 p-3 shadow-lg backdrop-blur-xl"
            >
              <Textarea
                ref={textareaRef}
                value={requirement}
                onChange={(e) => setRequirement(e.target.value)}
                placeholder={
                  refineMode
                    ? '描述需要调整的部分，例如：增加一个邮件通知步骤...'
                    : '描述你想要的工作流，例如：每天早上8点抓取科技新闻生成摘要推送到微信'
                }
                className="min-h-[140px] resize-none"
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                    e.preventDefault()
                    handleSubmit()
                  }
                }}
              />
              <div className="mt-2 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">
                  ⌘/Ctrl + Enter 提交 · Esc 关闭
                </span>
                <Button
                  size="sm"
                  onClick={handleSubmit}
                  disabled={loading || !requirement.trim()}
                >
                  {loading ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      生成中...
                    </>
                  ) : (
                    <>
                      <Sparkles className="h-4 w-4" />
                      {refineMode ? '调整工作流' : '生成工作流'}
                    </>
                  )}
                </Button>
              </div>
            </motion.div>
          )}
        </div>

        {/* 右部操作按钮 */}
        <div className="flex items-center gap-1 px-4">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onRefresh}
                disabled={actionsDisabled}
                aria-label="刷新"
                className="h-10 w-10 rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <RefreshCw className={cn('h-4 w-4', saving && 'animate-spin')} />
              </Button>
            </TooltipTrigger>
            <TooltipContent>刷新</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onSave}
                disabled={actionsDisabled || saving}
                aria-label="保存"
                className="h-10 w-10 rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                <Save className="h-4 w-4" />
              </Button>
            </TooltipTrigger>
            <TooltipContent>保存</TooltipContent>
          </Tooltip>
        </div>
      </header>
    </TooltipProvider>
  )
}
