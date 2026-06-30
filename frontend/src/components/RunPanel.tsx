// 工作流执行面板 - 触发执行并展示结果
import { useState, useRef, useMemo, useEffect } from 'react'
import type { ReactElement } from 'react'
import {
  CircleCheck,
  CircleX,
  SkipForward,
  Loader,
  TriangleAlert,
  Play,
  Check,
  X,
  Pause,
  ChevronDown,
  ChevronRight,
  Wrench,
  Bug,
  StepForward,
  Square,
} from 'lucide-react'
import type { ParseResponse, RunResult, StepResult } from '../types/workflow'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { ScrollArea } from '@/components/ui/ScrollArea'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/Select'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useToast } from '@/components/ui/Toast'
import { cn, extractApiError } from '@/lib/utils'
import { runWorkflowStream, stepNext, stepContinue, stepAbort } from '../services/api'

/** 实时日志条目 */
export interface LogEntry {
  time: string
  step_id: string
  event: 'start' | 'success' | 'failed' | 'skipped'
  message: string
  time_ms?: number
}

interface Props {
  workflow: ParseResponse | null
  runResult: RunResult | null
  onRun: () => void
  running: boolean
  logs?: LogEntry[]
  onFailure?: string
  onFailureChange?: (value: string) => void
  workflowId?: string
  /** B2: LLM 流式输出——当前各步骤累积的 token 文本(stepId → 已到达的文本) */
  streamingTokens?: Record<string, string>
}

const STATUS_ICON: Record<string, ReactElement> = {
  success: <CircleCheck size={16} />,
  failed: <CircleX size={16} />,
  skipped: <SkipForward size={16} />,
  running: <Loader size={16} className="animate-spin" />,
  partial_success: <TriangleAlert size={16} />,
  paused: <Pause size={16} />,
}

const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  skipped: '跳过',
  running: '执行中',
  partial_success: '部分成功',
  paused: '已暂停',
}

const LOG_EVENT_ICON: Record<LogEntry['event'], ReactElement> = {
  start: <Play size={14} />,
  success: <Check size={14} />,
  failed: <X size={14} />,
  skipped: <SkipForward size={14} />,
}

const LOG_EVENT_LABEL: Record<LogEntry['event'], string> = {
  start: '开始执行',
  success: '完成',
  failed: '失败',
  skipped: '跳过',
}

/** 步骤状态 → Badge variant 映射 */
function statusBadgeVariant(status: string): 'secondary' | 'destructive' | 'outline' {
  if (status === 'failed') return 'destructive'
  if (status === 'skipped' || status === 'pending') return 'outline'
  return 'secondary'
}

/** 将时间字符串格式化为 HH:MM:SS */
function formatLogTime(time: string): string {
  const d = new Date(time)
  if (!isNaN(d.getTime())) {
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  }
  // 非合法日期则原样返回（可能已是 HH:MM:SS）
  return time
}

/** 格式化输出为可展示的字符串 */
function formatOutput(output: unknown): string {
  if (output === null || output === undefined) return '(无输出)'
  if (typeof output === 'string') return output
  try {
    return JSON.stringify(output, null, 2)
  } catch {
    return String(output)
  }
}

/** 单步结果项 - 使用 Card 包裹，状态用 Badge */
function StepResultItem({
  stepName,
  toolIcon,
  result,
  streamingText,
}: {
  stepName: string
  toolIcon: string
  result: StepResult
  /** B2: 流式输出中累积的 token 文本(running 状态时显示,替代空输出) */
  streamingText?: string
}) {
  // 输出折叠状态：长输出（>200 字符）默认折叠，短输出默认展开
  const outputStr = formatOutput(result.output)
  const hasOutput = result.status === 'success' && result.output !== null && result.output !== undefined
  const isLongOutput = outputStr.length > 200
  const [outputExpanded, setOutputExpanded] = useState(!isLongOutput)
  // 点击步骤标题切换输出显示/隐藏（仅在有输出时生效）
  const [outputVisible, setOutputVisible] = useState(hasOutput && !isLongOutput)
  // 错误详情折叠状态：长错误默认折叠，点击展开查看完整信息
  const errorStr = result.error || ''
  const isLongError = errorStr.length > 200
  const [errorExpanded, setErrorExpanded] = useState(!isLongError)
  const displayOutput = outputExpanded ? outputStr : outputStr.slice(0, 200)
  const displayError = errorExpanded ? errorStr : errorStr.slice(0, 200)

  const toggleOutput = () => {
    if (!hasOutput) return
    setOutputVisible((v) => !v)
  }

  return (
    <Card
      className={cn(
        'p-3',
        // 失败步骤红色边条
        result.status === 'failed' && 'border-l-2 border-l-destructive'
      )}
    >
      <div
        className={cn(
          'flex items-center gap-2',
          hasOutput && 'cursor-pointer'
        )}
        onClick={toggleOutput}
      >
        <span className="shrink-0">{STATUS_ICON[result.status]}</span>
        <span className="flex-1 truncate text-sm font-medium">
          {toolIcon ? <span>{toolIcon}</span> : <Wrench className="inline h-3.5 w-3.5" />} {stepName}
        </span>
        <Badge variant={statusBadgeVariant(result.status)} className={cn(result.status === 'running' && 'animate-pulse')}>
          {STATUS_LABEL[result.status]}
        </Badge>
        {result.time_ms !== undefined && (
          <span className="text-xs text-muted-foreground">{result.time_ms} ms</span>
        )}
        {hasOutput && (
          <span className="shrink-0 text-muted-foreground">
            {outputVisible ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        )}
      </div>
      {result.error && (
        <div
          className="mt-2 rounded bg-destructive/10 p-2 text-xs text-destructive"
          onClick={() => isLongError && setErrorExpanded((v) => !v)}
          role={isLongError ? 'button' : undefined}
        >
          <span className="font-semibold">错误: </span>
          {displayError}{isLongError && !errorExpanded ? '...(截断)' : ''}
          {isLongError && (
            <span className="ml-1 underline">
              {errorExpanded ? ' [收起]' : ' [展开全部]'}
            </span>
          )}
        </div>
      )}
      {/* B2: LLM 流式输出——running 状态且有 streamingText 时显示实时 token 流(带光标动画) */}
      {result.status === 'running' && streamingText && (
        <div className="mt-2">
          <span className="text-xs text-muted-foreground">流式输出中</span>
          <pre className="mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2 text-xs whitespace-pre-wrap break-all">
            {streamingText}
            <span className="inline-block w-1.5 h-3 ml-0.5 bg-primary animate-pulse align-middle" />
          </pre>
        </div>
      )}
      {hasOutput && outputVisible && (
        <div className="mt-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">输出</span>
            {isLongOutput && (
              <Button
                variant="outline"
                size="sm"
                className="h-6 text-xs"
                onClick={(e) => {
                  e.stopPropagation()
                  setOutputExpanded(!outputExpanded)
                }}
              >
                {outputExpanded ? '收起' : '展开全部'}
              </Button>
            )}
          </div>
          <pre className="mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2 text-xs whitespace-pre-wrap break-all">
            {displayOutput}{isLongOutput && !outputExpanded ? '...(截断)' : ''}
          </pre>
        </div>
      )}
    </Card>
  )
}

export function RunPanel({ workflow, runResult, onRun, running, logs, onFailure, onFailureChange, workflowId, streamingTokens }: Props) {
  const toast = useToast()
  // 调试模式开关（持久化到 localStorage）
  const [debugMode, setDebugMode] = useState<boolean>(
    () => localStorage.getItem('flowgenie_debug_mode') === 'true'
  )
  // 调试执行状态：独立于父组件的 running/runResult（父组件不感知调试执行）
  const [debugRunning, setDebugRunning] = useState(false)
  const [debugRunResult, setDebugRunResult] = useState<RunResult | null>(null)
  const [debugRunId, setDebugRunId] = useState<string | null>(null)
  const [debugLogs, setDebugLogs] = useState<LogEntry[]>([])
  // B2: 调试模式下的流式 token(独立于父组件的 streamingTokens)
  const [debugStreamingTokens, setDebugStreamingTokens] = useState<Record<string, string>>({})
  const [showAbortConfirm, setShowAbortConfirm] = useState(false)
  const debugAbortRef = useRef<AbortController | null>(null)

  // 调试模式下的有效状态（调试模式用本地状态，否则用父组件传入的 props）
  const effectiveRunResult = debugMode ? debugRunResult : runResult
  const effectiveRunning = debugMode ? debugRunning : running
  // B2: 调试模式用本地 token 状态,普通模式用父组件传入的 streamingTokens
  const effectiveStreamingTokens = debugMode ? debugStreamingTokens : streamingTokens
  const effectiveLogs = debugMode ? debugLogs : logs
  // 当前运行 ID（调试模式下来自 start 事件，普通模式下 RunResult 可能无 id）
  const currentRunId = debugMode ? debugRunId : (runResult?.id ?? null)

  const canRun = !!workflow && workflow.steps.length > 0 && !effectiveRunning
  const hasLogs = !!effectiveLogs && effectiveLogs.length > 0

  // 进度计算：已完成步骤数（success/failed/skipped）/ 总步骤数
  // 若 running 但无 runResult（步骤数未知）→ indeterminate 模式
  const totalSteps = workflow?.steps.length ?? 0
  const completedSteps = effectiveRunResult
    ? Object.values(effectiveRunResult.steps_result).filter(
        (r) => r.status === 'success' || r.status === 'failed' || r.status === 'skipped'
      ).length
    : 0
  const showProgressBar = effectiveRunning && workflow
  const isIndeterminate = effectiveRunning && (!effectiveRunResult || Object.keys(effectiveRunResult.steps_result).length === 0)
  const progressPercent = totalSteps > 0 && !isIndeterminate
    ? Math.min(100, Math.round((completedSteps / totalSteps) * 100))
    : 0

  // 当前步骤：优先找 status==='running'，否则取最后完成的步骤（用于"当前步骤"提示）
  const currentStepId = useMemo(() => {
    const sr = effectiveRunResult?.steps_result
    if (!sr) return null
    const runningEntry = Object.entries(sr).find(([, r]) => r.status === 'running')
    if (runningEntry) return runningEntry[0]
    return null
  }, [effectiveRunResult])
  const currentStepName = useMemo(() => {
    if (!currentStepId || !workflow) return null
    return workflow.steps.find((s) => s.id === currentStepId)?.name ?? currentStepId
  }, [currentStepId, workflow])

  // 调试模式切换：运行中不允许切换
  const handleToggleDebug = (enabled: boolean) => {
    if (effectiveRunning) return
    setDebugMode(enabled)
    localStorage.setItem('flowgenie_debug_mode', String(enabled))
    // 切换时清空调试执行残留
    setDebugRunResult(null)
    setDebugRunId(null)
    setDebugLogs([])
  }

  // 调试执行：直接调用 runWorkflowStream（带 debug=true），由 RunPanel 自行管理状态
  const handleDebugRun = () => {
    if (!workflow || debugRunning) return
    if (!workflowId) {
      toast.error('请先保存工作流后再调试执行')
      return
    }
    setDebugRunning(true)
    setDebugRunResult(null)
    setDebugLogs([])
    setDebugRunId(null)
    setDebugStreamingTokens({}) // B2: 清空上次调试流式 token
    const controller = runWorkflowStream(
      workflow,
      // onStep：每步完成即标记为 paused（调试模式每步后暂停）
      (data) => {
        setDebugRunResult((prev) => ({
          id: prev?.id,
          status: data.status === 'running' ? 'running' : 'paused',
          steps_result: {
            ...(prev?.steps_result || {}),
            [data.step_id]: {
              output: data.output,
              status: data.status as StepResult['status'],
              error: data.error,
              time_ms: data.time_ms,
            },
          },
          total_time_ms: prev?.total_time_ms || 0,
        }))
        // running 状态只更新步骤状态，不添加完成日志
        if (data.status === 'running') return
        // B2: 步骤完成时清除该步骤的流式 token
        setDebugStreamingTokens((prev) => {
          if (!(data.step_id in prev)) return prev
          const next = { ...prev }
          delete next[data.step_id]
          return next
        })
        setDebugLogs((prev) => [
          ...prev,
          {
            time: new Date().toISOString(),
            step_id: data.step_id,
            event: data.status as 'success' | 'failed' | 'skipped',
            message: data.error || '',
            time_ms: data.time_ms,
          },
        ])
      },
      // onDone：合并最终状态
      (data) => {
        setDebugRunResult((prev) => ({
          id: prev?.id,
          status: data.status as RunResult['status'],
          steps_result: {
            ...(prev?.steps_result || {}),
            ...(data.steps_result as Record<string, StepResult>),
          },
          total_time_ms: data.total_time_ms,
        }))
        setDebugStreamingTokens({}) // B2: 执行完成清空流式 token
        setDebugRunning(false)
      },
      // onError
      (errMsg) => {
        toast.error(errMsg)
        setDebugStreamingTokens({}) // B2: 出错时清空流式 token
        setDebugRunning(false)
        setDebugRunResult((prev) => (prev ? { ...prev, status: 'failed' } : prev))
      },
      {
        workflow_id: workflowId,
        on_failure: onFailure,
        debug: true,
        onStart: (data) => {
          if (data.run_id) setDebugRunId(data.run_id)
        },
        // B2: LLM 流式 token 增量回调
        onStepToken: (stepId, delta) => {
          setDebugStreamingTokens((prev) => ({
            ...prev,
            [stepId]: (prev[stepId] || '') + delta,
          }))
        },
      }
    )
    debugAbortRef.current = controller
  }

  // 单步控制：下一步
  const handleStepNext = async () => {
    if (!workflowId || !currentRunId) return
    try {
      await stepNext(workflowId, currentRunId)
      // 乐观更新：标记为 running，等待 SSE 推送下一步
      setDebugRunResult((prev) => (prev ? { ...prev, status: 'running' } : prev))
    } catch (e) {
      toast.error(extractApiError(e) || '下一步失败')
    }
  }

  // 单步控制：全速继续
  const handleStepContinue = async () => {
    if (!workflowId || !currentRunId) return
    try {
      await stepContinue(workflowId, currentRunId)
      setDebugRunResult((prev) => (prev ? { ...prev, status: 'running' } : prev))
      toast.info('已切换为全速执行')
    } catch (e) {
      toast.error(extractApiError(e) || '继续执行失败')
    }
  }

  // 单步控制：中止（带确认）
  const handleStepAbort = async () => {
    setShowAbortConfirm(false)
    if (!workflowId || !currentRunId) return
    try {
      await stepAbort(workflowId, currentRunId)
      // 乐观标记为 aborted，等待 SSE error 事件结束流
      setDebugRunResult((prev) => (prev ? { ...prev, status: 'aborted' as RunResult['status'] } : prev))
      toast.info('已发送中止指令')
    } catch (e) {
      toast.error(extractApiError(e) || '中止失败')
    }
  }

  // 卸载或切换调试模式时中止未完成的调试流
  useEffect(() => {
    return () => {
      if (debugAbortRef.current) {
        debugAbortRef.current.abort()
        debugAbortRef.current = null
      }
    }
  }, [])

  const isPaused = effectiveRunResult?.status === 'paused'

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border p-3">
        <h3 className="text-base font-semibold">执行工作流</h3>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {!workflow ? (
          <p className="text-sm text-muted-foreground">请先生成工作流</p>
        ) : (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => (debugMode ? handleDebugRun() : onRun())} disabled={!canRun}>
                {effectiveRunning ? (
                  <>
                    <Loader size={16} className="animate-spin" /> 执行中...
                  </>
                ) : debugMode ? (
                  <>
                    <Bug size={16} /> 调试执行
                  </>
                ) : (
                  <>
                    <Play size={16} /> 执行工作流
                  </>
                )}
              </Button>
              <span className="text-xs text-muted-foreground">{workflow.steps.length} 个步骤</span>
              {/* 调试模式开关（运行中禁用） */}
              <Button
                variant={debugMode ? 'default' : 'outline'}
                size="sm"
                className="h-8 gap-1 text-xs"
                onClick={() => handleToggleDebug(!debugMode)}
                disabled={effectiveRunning}
                title="开启后每步执行完成暂停，可单步/继续/中止"
              >
                <Bug size={14} /> 调试模式
              </Button>
              {onFailureChange && (
                <Select
                  value={onFailure || 'stop'}
                  onValueChange={(v) => onFailureChange(v)}
                >
                  <SelectTrigger className="h-8 w-32 text-xs" title="失败策略：stop=失败即停，continue=失败继续">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="stop">失败即停</SelectItem>
                    <SelectItem value="continue">失败继续</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </div>

            {/* 调试模式单步控制：暂停时显示下一步/继续/中止 */}
            {isPaused && (
              <div className="flex flex-wrap items-center gap-2 rounded-md border border-primary/40 bg-primary/5 p-2">
                <span className="text-xs font-medium text-primary">已暂停 — 等待下一步指令</span>
                {currentStepName && (
                  <span className="text-xs text-muted-foreground">当前步骤: {currentStepName}</span>
                )}
                <div className="ml-auto flex items-center gap-2">
                  <Button size="sm" className="h-8 gap-1 text-xs" onClick={handleStepNext}>
                    <StepForward size={14} /> 下一步
                  </Button>
                  <Button size="sm" variant="outline" className="h-8 gap-1 text-xs" onClick={handleStepContinue}>
                    <Play size={14} /> 继续
                  </Button>
                  <Button size="sm" variant="destructive" className="h-8 gap-1 text-xs" onClick={() => setShowAbortConfirm(true)}>
                    <Square size={14} /> 中止
                  </Button>
                </div>
              </div>
            )}

            {/* 执行进度条：indeterminate（步骤数未知时滑动）或 determinate（步骤 X/Y） */}
            {showProgressBar && (
              <div className="flex flex-col gap-1">
                {isIndeterminate ? (
                  <div
                    className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-busy="true"
                    aria-label="执行中"
                  >
                    <div className="progress-indeterminate h-full w-1/3 rounded-full bg-primary" />
                  </div>
                ) : (
                  <>
                    <div className="text-xs text-muted-foreground">
                      步骤 {completedSteps}/{totalSteps}
                    </div>
                    <div
                      className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
                      role="progressbar"
                      aria-valuenow={progressPercent}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      aria-label={`步骤进度 ${completedSteps} / ${totalSteps}`}
                    >
                      <div
                        className="h-full rounded-full bg-primary transition-all duration-300"
                        style={{ width: `${progressPercent}%` }}
                      />
                    </div>
                  </>
                )}
              </div>
            )}

            {hasLogs && (
              <div className="flex flex-col gap-1">
                <div className="text-xs font-medium text-muted-foreground">实时日志</div>
                <ScrollArea className="h-[200px] w-full rounded-md border border-border bg-muted/30 p-2">
                  <div className="flex flex-col gap-0.5 font-mono text-xs">
                    {effectiveLogs!.map((log, i) => (
                      <div key={i} className="flex flex-wrap items-center gap-x-1 gap-y-0.5">
                        <span className="text-muted-foreground">[{formatLogTime(log.time)}]</span>
                        <span className="shrink-0">{LOG_EVENT_ICON[log.event]}</span>
                        <span className="shrink-0 font-medium">{log.step_id}</span>
                        <span className="break-all">
                          {LOG_EVENT_LABEL[log.event]}
                          {log.event === 'success' && log.time_ms !== undefined
                            ? ` (${log.time_ms}ms)`
                            : ''}
                          {log.event === 'failed' && log.message
                            ? `: ${log.message}`
                            : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </div>
            )}

            {effectiveRunResult && (
              <div className="flex flex-col gap-1.5 rounded-md border border-border bg-card/40 p-3">
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">总状态:</span>
                  <Badge variant={statusBadgeVariant(effectiveRunResult.status)} className={cn((effectiveRunResult.status === 'running' || effectiveRunResult.status === 'paused') && 'animate-pulse')}>
                    {effectiveRunResult.status === 'success' ? (
                      <span className="flex items-center gap-1"><CircleCheck size={14} /> 成功</span>
                    ) : effectiveRunResult.status === 'running' ? (
                      <span className="flex items-center gap-1"><Loader size={14} className="animate-spin" /> 执行中</span>
                    ) : effectiveRunResult.status === 'paused' ? (
                      <span className="flex items-center gap-1"><Pause size={14} /> 已暂停</span>
                    ) : effectiveRunResult.status === 'partial_success' ? (
                      <span className="flex items-center gap-1"><TriangleAlert size={14} /> 部分成功</span>
                    ) : effectiveRunResult.status === 'aborted' ? (
                      <span className="flex items-center gap-1"><CircleX size={14} /> 已中止</span>
                    ) : (
                      <span className="flex items-center gap-1"><CircleX size={14} /> 失败</span>
                    )}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-sm">
                  <span className="text-muted-foreground">总耗时:</span>
                  <span className="text-xs">{effectiveRunResult.total_time_ms} ms</span>
                </div>
              </div>
            )}

            {effectiveRunResult && (
              <div className="flex flex-col gap-2">
                <h4 className="text-sm font-semibold">步骤结果</h4>
                {workflow.steps.map((step) => {
                  const result = effectiveRunResult.steps_result[step.id]
                  if (!result) {
                    return (
                      <Card key={step.id} className="p-3 opacity-60">
                        <div className="flex items-center gap-2">
                          <span className="shrink-0 text-muted-foreground">
                            <Pause size={16} />
                          </span>
                          <span className="flex-1 truncate text-sm font-medium">
                            {step.tool_info?.icon ? <span>{step.tool_info.icon}</span> : <Wrench className="inline h-3.5 w-3.5" />} {step.name}
                          </span>
                          <Badge variant="outline">未执行</Badge>
                        </div>
                      </Card>
                    )
                  }
                  return (
                    <StepResultItem
                      key={step.id}
                      stepName={step.name}
                      toolIcon={step.tool_info?.icon || ''}
                      result={result}
                      streamingText={effectiveStreamingTokens?.[step.id]}
                    />
                  )
                })}
              </div>
            )}
          </div>
        )}
      </div>
      {/* 调试模式中止确认对话框 */}
      <ConfirmDialog
        open={showAbortConfirm}
        title="中止调试执行"
        message="确定要中止当前调试执行吗？未完成的步骤将被跳过。"
        confirmText="中止"
        cancelText="取消"
        danger
        onConfirm={handleStepAbort}
        onCancel={() => setShowAbortConfirm(false)}
      />
    </div>
  )
}
