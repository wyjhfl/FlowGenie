// RunHistory 子组件与共享 helpers(从 RunHistory.tsx 抽出)
// - StepCards: 结构化步骤结果卡片(可展开输出/错误)
// - RunLogs: 执行日志区(可折叠)
// - RunDiffPanel: 两次执行对比 diff 模态面板
// 均用 React.memo 包裹,避免父组件无关状态变更(如 compareIds/retry)触发全量重渲染。
import { memo } from 'react'
import type { ReactElement } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import type { RunDiff } from '../services/api'
import type { WorkflowStep } from '../types/workflow'
import {
  Wrench,
  CircleCheck,
  CircleX,
  TriangleAlert,
  Loader,
  ChevronDown,
  ChevronRight,
  GitCompare,
  X,
  Clock,
} from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Separator } from '@/components/ui/Separator'
import { cn } from '@/lib/utils'

// ===== 共享类型 =====

export interface StepResultInfo {
  output?: unknown
  status?: string
  error?: string | null
  time_ms?: number
}

export interface RunLogEntry {
  timestamp: number
  level: string
  module: string
  message: string
}

// ===== 共享 helpers =====

/** 将输出值转为字符串 */
export function stringifyOutput(output: unknown): string {
  if (output === null || output === undefined) return ''
  if (typeof output === 'string') return output
  try {
    return JSON.stringify(output, null, 2)
  } catch {
    return String(output)
  }
}

/** 按 step_id 自然顺序排序(step_1, step_2, ... step_10),无法解析时保持原序 */
export function sortStepIds(ids: string[]): string[] {
  const numKey = (id: string): number | null => {
    const m = id.match(/(\d+)$/)
    return m ? parseInt(m[1], 10) : null
  }
  const indexed = ids.map((id, idx) => ({ id, idx, n: numKey(id) }))
  indexed.sort((a, b) => {
    if (a.n !== null && b.n !== null) return a.n - b.n
    if (a.n !== null) return -1
    if (b.n !== null) return 1
    return a.idx - b.idx
  })
  return indexed.map((x) => x.id)
}

/** 步骤状态 → Badge variant 映射 */
export function stepBadgeVariant(status: string): 'secondary' | 'destructive' | 'outline' {
  if (status === 'failed') return 'destructive'
  if (status === 'skipped' || status === 'paused') return 'outline'
  return 'secondary'
}

/** 状态文本:用 lucide 图标替代 emoji,返回 ReactElement */
export function statusText(s: string): ReactElement {
  if (s === 'success') return <span className="flex items-center gap-1"><CircleCheck size={14} /> 成功</span>
  if (s === 'failed') return <span className="flex items-center gap-1"><CircleX size={14} /> 失败</span>
  if (s === 'partial_success') return <span className="flex items-center gap-1"><TriangleAlert size={14} /> 部分成功</span>
  if (s === 'running') return <span className="flex items-center gap-1"><Loader size={14} className="animate-spin" /> 运行中</span>
  if (s === 'paused') return <span className="flex items-center gap-1 text-warning"><Clock size={14} /> 待审批</span>
  return <span>{s}</span>
}

export function triggerText(t: string) {
  return (
    {
      manual: '手动',
      schedule: '定时',
      webhook: 'Webhook',
    } as Record<string, string>
  )[t] || t
}

export function stepStatusText(s: string) {
  return (
    {
      success: '成功',
      failed: '失败',
      skipped: '跳过',
      running: '运行中',
    } as Record<string, string>
  )[s] || s
}

/** 格式化 ISO 时间为本地时区字符串(后端返回 UTC 无时区后缀,补 'Z' 后再解析) */
export function formatLocalTime(iso: string | null | undefined): string {
  if (!iso) return '-'
  try {
    const hasTz = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso)
    const normalized = hasTz ? iso : iso + 'Z'
    return new Date(normalized).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return iso.replace('T', ' ').slice(0, 19)
  }
}

/** 格式化日志时间戳为 HH:MM:SS.mmm */
export function formatLogTime(ts: number): string {
  const d = new Date(ts * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  const ms = String(d.getMilliseconds()).padStart(3, '0')
  return `${hh}:${mm}:${ss}.${ms}`
}

// ===== 输出可视化 =====

type OutputVizType = 'table' | 'bar' | 'pie' | 'json'

function detectOutputType(output: unknown): OutputVizType {
  if (!output || typeof output !== 'object' || Array.isArray(output)) return 'json'
  const obj = output as Record<string, unknown>
  const items = obj.items
  const isItemsListOfDict =
    Array.isArray(items) &&
    items.length > 0 &&
    items.every((it) => it && typeof it === 'object' && !Array.isArray(it))
  const isLabelValueItems =
    isItemsListOfDict &&
    (items as Array<Record<string, unknown>>).every(
      (it) => typeof it.label === 'string' && typeof it.value === 'number'
    )
  if (isLabelValueItems) {
    const values = (items as Array<{ value: number }>).map((it) => it.value)
    const sum = values.reduce((s, v) => s + v, 0)
    if (sum >= 95 && sum <= 105) return 'pie'
    return 'bar'
  }
  const rows = obj.rows
  if (
    Array.isArray(rows) &&
    rows.length > 0 &&
    typeof rows[0] === 'object' &&
    !Array.isArray(rows[0])
  ) {
    return 'table'
  }
  if (isItemsListOfDict) {
    return 'table'
  }
  return 'json'
}

function TableView({ output }: { output: Record<string, unknown> }) {
  const rawRows = (output.rows ?? output.items) as Array<Record<string, unknown>> | undefined
  if (!rawRows || rawRows.length === 0) return null
  let columns: string[] = []
  if (Array.isArray(output.columns) && output.columns.length > 0) {
    columns = output.columns.map((c) => String(c))
  } else {
    columns = Object.keys(rawRows[0])
  }
  const displayRows = rawRows.slice(0, 50)
  const total = rawRows.length
  return (
    <div className="mt-1 max-h-60 overflow-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c} className="border border-border px-2 py-1 bg-muted text-left">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {displayRows.map((row, i) => (
            <tr key={i}>
              {columns.map((c) => {
                const cell = row[c]
                const text =
                  cell === null || cell === undefined
                    ? ''
                    : typeof cell === 'object'
                    ? JSON.stringify(cell)
                    : String(cell)
                return (
                  <td key={c} className="border border-border px-2 py-1 align-top">
                    {text}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
      {total > 50 && (
        <div className="mt-1 text-xs text-muted-foreground">显示前 50 行,共 {total} 行</div>
      )}
    </div>
  )
}

function BarChart({ items }: { items: { label: string; value: number }[] }) {
  const max = Math.max(...items.map((i) => i.value), 1)
  const barWidth = 40
  const gap = 10
  const width = items.length * (barWidth + gap)
  const height = 250
  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 250 }}>
      {items.map((item, i) => {
        const barHeight = (item.value / max) * 200
        const x = i * (barWidth + gap)
        const y = 220 - barHeight
        return (
          <g key={i}>
            <rect x={x} y={y} width={barWidth} height={barHeight} fill="hsl(var(--primary))" />
            <text x={x + barWidth / 2} y={y - 5} textAnchor="middle" className="fill-foreground" fontSize="10">
              {item.value}
            </text>
            <text x={x + barWidth / 2} y={235} textAnchor="middle" className="fill-muted-foreground" fontSize="10">
              {item.label.length > 10 ? item.label.slice(0, 10) + '…' : item.label}
            </text>
          </g>
        )
      })}
    </svg>
  )
}

function PieChart({ items }: { items: { label: string; value: number }[] }) {
  const total = items.reduce((sum, i) => sum + i.value, 0)
  let cumulative = 0
  const cx = 100, cy = 100, r = 80
  const colors = items.map((_, i) => `hsl(${(i * 360 / items.length)}, 70%, 55%)`)
  return (
    <div className="flex gap-4">
      <svg viewBox="0 0 200 200" width={200} height={200}>
        {items.map((item, i) => {
          const startAngle = (cumulative / total) * 2 * Math.PI - Math.PI / 2
          cumulative += item.value
          const endAngle = (cumulative / total) * 2 * Math.PI - Math.PI / 2
          const x1 = cx + r * Math.cos(startAngle)
          const y1 = cy + r * Math.sin(startAngle)
          const x2 = cx + r * Math.cos(endAngle)
          const y2 = cy + r * Math.sin(endAngle)
          const largeArc = (item.value / total) > 0.5 ? 1 : 0
          const path = `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2} Z`
          return <path key={i} d={path} fill={colors[i]} />
        })}
      </svg>
      <ul className="text-xs space-y-1">
        {items.map((item, i) => (
          <li key={i} className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: colors[i] }} />
            <span>{item.label}: {((item.value / total) * 100).toFixed(1)}%</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function RenderStepOutput({ output }: { output: unknown }) {
  const type = detectOutputType(output)
  if (type === 'table' && output && typeof output === 'object') {
    return <TableView output={output as Record<string, unknown>} />
  }
  if ((type === 'bar' || type === 'pie') && output && typeof output === 'object') {
    const items = (output as { items: { label: string; value: number }[] }).items
    return type === 'bar' ? <BarChart items={items} /> : <PieChart items={items} />
  }
  const text = stringifyOutput(output)
  if (!text) return null
  return (
    <pre className="mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2 text-xs whitespace-pre-wrap break-all">
      {text}
    </pre>
  )
}

// ===== StepCards: 结构化步骤结果卡片 =====

interface StepCardsProps {
  stepsResult: Record<string, unknown>
  stepMap: Record<string, WorkflowStep>
  runId: string | undefined
  expandedOutputs: Set<string>
  expandedErrors: Set<string>
  onToggleOutput: (key: string) => void
  onToggleError: (key: string) => void
}

export const StepCards = memo(function StepCards({
  stepsResult,
  stepMap,
  runId,
  expandedOutputs,
  expandedErrors,
  onToggleOutput,
  onToggleError,
}: StepCardsProps) {
  const ids = sortStepIds(Object.keys(stepsResult))
  if (ids.length === 0) {
    return <p className="py-2 text-sm text-muted-foreground">无步骤结果</p>
  }
  return (
    <div className="flex flex-col gap-2">
      {ids.map((sid, idx) => {
        const sr = (stepsResult[sid] as StepResultInfo) || {}
        const stepInfo = stepMap[sid]
        const status = sr.status || 'unknown'
        const icon = stepInfo?.tool_info?.icon
        const name = stepInfo?.name || sid
        const timeMs = typeof sr.time_ms === 'number' ? sr.time_ms : undefined
        const outputStr = stringifyOutput(sr.output)
        const truncated = outputStr.length > 200
        const outputSummary = truncated ? outputStr.slice(0, 200) + '...' : outputStr
        const outputKey = `${runId}-${sid}-output`
        const outputExpanded = expandedOutputs.has(outputKey)
        const outputType = detectOutputType(sr.output)
        const errorStr = sr.error || ''
        const errorTruncated = errorStr.length > 200
        const errorSummary = errorTruncated ? errorStr.slice(0, 200) + '...' : errorStr
        const errorKey = `${runId}-${sid}-error`
        const errorExpanded = expandedErrors.has(errorKey)

        return (
          <div key={sid}>
            {idx > 0 && <Separator />}
            <div
              className={cn(
                'relative rounded-md border border-border bg-card/40 p-3',
                status === 'failed' && 'border-l-2 border-l-destructive'
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="outline" className="h-5 w-5 justify-center rounded-full p-0 text-[10px]">
                  {idx + 1}
                </Badge>
                {icon ? <span className="text-base">{icon}</span> : <Wrench className="h-4 w-4" />}
                <span className="flex-1 truncate text-sm font-medium">{name}</span>
                <Badge
                  variant={stepBadgeVariant(status)}
                  className={cn(status === 'running' && 'animate-pulse')}
                >
                  {stepStatusText(status)}
                </Badge>
                {timeMs !== undefined && (
                  <span className="text-xs text-muted-foreground">{timeMs}ms</span>
                )}
              </div>
              {outputStr && (
                <div className="mt-2">
                  <div className="text-xs text-muted-foreground">输出:</div>
                  {outputType === 'json' ? (
                    <>
                      <pre className="mt-1 max-h-60 overflow-auto rounded bg-muted/40 p-2 text-xs whitespace-pre-wrap break-all">
                        {outputExpanded ? outputStr : outputSummary}
                      </pre>
                      {truncated && (
                        <Button
                          variant="link"
                          size="sm"
                          className="h-6 px-0 text-xs"
                          onClick={(e) => {
                            e.stopPropagation()
                            onToggleOutput(outputKey)
                          }}
                        >
                          {outputExpanded ? '收起' : '展开全部'}
                        </Button>
                      )}
                    </>
                  ) : (
                    <RenderStepOutput output={sr.output} />
                  )}
                </div>
              )}
              {status === 'failed' && errorStr && (
                <div className="mt-2">
                  <div className="text-xs text-destructive">错误:</div>
                  <pre className="mt-1 max-h-60 overflow-auto rounded bg-destructive/10 p-2 text-xs whitespace-pre-wrap break-all text-destructive">
                    {errorExpanded ? errorStr : errorSummary}
                  </pre>
                  {errorTruncated && (
                    <Button
                      variant="link"
                      size="sm"
                      className="h-6 px-0 text-xs"
                      onClick={(e) => {
                        e.stopPropagation()
                        onToggleError(errorKey)
                      }}
                    >
                      {errorExpanded ? '收起' : '展开全部'}
                    </Button>
                  )}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
})

// ===== RunLogs: 执行日志区(可折叠) =====

interface RunLogsProps {
  runId: string
  logs: RunLogEntry[]
  isExpanded: boolean
  onToggle: (runId: string) => void
}

export const RunLogs = memo(function RunLogs({ runId, logs, isExpanded, onToggle }: RunLogsProps) {
  if (!logs || logs.length === 0) return null
  return (
    <div className="mt-2">
      <Button
        variant="ghost"
        size="sm"
        className="h-6 px-1 text-xs text-muted-foreground"
        aria-expanded={isExpanded}
        aria-controls={`logs-${runId}`}
        onClick={(e) => {
          e.stopPropagation()
          onToggle(runId)
        }}
      >
        {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />} 执行日志 ({logs.length})
      </Button>
      {isExpanded && (
        <div id={`logs-${runId}`} className="mt-1 max-h-60 overflow-auto rounded-md bg-muted/40 p-2 font-mono text-xs">
          {logs.map((log, idx) => {
            const lvl = log.level.toLowerCase()
            return (
              <div
                key={idx}
                className={cn(
                  'flex flex-wrap items-center gap-x-1 gap-y-0.5',
                  lvl === 'error' && 'text-destructive',
                  lvl === 'warning' && 'text-warning'
                )}
              >
                <span className="text-muted-foreground">{formatLogTime(log.timestamp)}</span>
                <span className="font-semibold uppercase">{log.level}</span>
                <span className="text-muted-foreground">[{log.module}]</span>
                <span className="break-all">{log.message}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
})

// ===== RunDiffPanel: 两次执行对比 diff 模态 =====

interface RunDiffPanelProps {
  diffResult: RunDiff | null
  diffLoading: boolean
  diffError: string | null
  onClose: () => void
}

export const RunDiffPanel = memo(function RunDiffPanel({
  diffResult,
  diffLoading,
  diffError,
  onClose,
}: RunDiffPanelProps) {
  return (
    <AnimatePresence>
      {(diffResult || diffLoading || diffError) && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4"
          onClick={onClose}
        >
          <motion.div
            initial={{ scale: 0.95, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.95, opacity: 0 }}
            className="flex max-h-[85vh] w-full max-w-4xl flex-col overflow-hidden rounded-lg border border-border bg-card shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            {/* diff 面板头部 */}
            <div className="flex items-center justify-between border-b border-border p-3">
              <h3 className="flex items-center gap-2 text-base font-semibold">
                <GitCompare size={16} /> 执行对比
              </h3>
              <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
                <X size={14} />
              </Button>
            </div>
            {/* diff 内容 */}
            <div className="flex-1 overflow-y-auto p-3">
              {diffLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader size={20} className="animate-spin text-muted-foreground" />
                  <span className="ml-2 text-sm text-muted-foreground">加载对比数据...</span>
                </div>
              ) : diffError ? (
                <div className="flex items-center gap-2 rounded-md bg-destructive/10 p-3 text-sm text-destructive">
                  <TriangleAlert size={16} /> {diffError}
                </div>
              ) : diffResult ? (
                <>
                  {/* 两次执行概要 */}
                  <div className="mb-3 grid grid-cols-2 gap-3">
                    {[diffResult.run1, diffResult.run2].map((run, i) => (
                      <div key={i} className="rounded-md border border-border bg-card/40 p-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={stepBadgeVariant(run.status)}>
                            {statusText(run.status)}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {triggerText(run.trigger_type)}
                          </span>
                        </div>
                        <div className="mt-1 flex justify-between text-xs text-muted-foreground">
                          <span>{formatLocalTime(run.started_at)}</span>
                          <span>{run.total_time_ms}ms</span>
                        </div>
                        <div className="mt-0.5 text-xs text-muted-foreground">
                          Run ID: {run.id.slice(0, 8)}...
                        </div>
                      </div>
                    ))}
                  </div>
                  {/* 步骤对比表格 */}
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="border-b border-border text-muted-foreground">
                          <th className="py-1.5 pr-2 text-left font-medium">#</th>
                          <th className="py-1.5 pr-2 text-left font-medium">步骤名称</th>
                          <th className="py-1.5 pr-2 text-center font-medium">执行 1 状态</th>
                          <th className="py-1.5 pr-2 text-center font-medium">执行 2 状态</th>
                          <th className="py-1.5 pr-2 text-right font-medium">执行 1 耗时</th>
                          <th className="py-1.5 text-right font-medium">执行 2 耗时</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diffResult.steps.map((step, i) => (
                          <tr
                            key={step.step_id}
                            className={cn(
                              'border-b border-border/50',
                              step.changed && 'bg-warning/10'
                            )}
                          >
                            <td className="py-1.5 pr-2 text-muted-foreground">{i + 1}</td>
                            <td className="py-1.5 pr-2">
                              <span className="truncate" title={step.name}>{step.name}</span>
                            </td>
                            <td className="py-1.5 pr-2 text-center">
                              {step.status1 ? (
                                <Badge variant={stepBadgeVariant(step.status1)} className="text-[10px]">
                                  {stepStatusText(step.status1)}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </td>
                            <td className="py-1.5 pr-2 text-center">
                              {step.status2 ? (
                                <Badge variant={stepBadgeVariant(step.status2)} className="text-[10px]">
                                  {stepStatusText(step.status2)}
                                </Badge>
                              ) : (
                                <span className="text-muted-foreground">-</span>
                              )}
                            </td>
                            <td className="py-1.5 pr-2 text-right text-muted-foreground">
                              {step.time1 != null ? `${step.time1}ms` : '-'}
                            </td>
                            <td className="py-1.5 text-right text-muted-foreground">
                              {step.time2 != null ? `${step.time2}ms` : '-'}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {/* 错误详情(仅显示有变化的错误) */}
                  {diffResult.steps.some((s) => s.changed && (s.error1 || s.error2)) && (
                    <div className="mt-3">
                      <div className="mb-1 text-xs font-medium text-muted-foreground">错误变化详情:</div>
                      {diffResult.steps
                        .filter((s) => s.changed && (s.error1 || s.error2))
                        .map((step) => (
                          <div key={step.step_id} className="mb-2 rounded-md border border-border p-2">
                            <div className="text-xs font-medium">{step.name}</div>
                            {step.error1 && (
                              <div className="mt-1">
                                <span className="text-xs text-muted-foreground">执行 1:</span>
                                <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-destructive/10 p-1.5 text-xs whitespace-pre-wrap break-all text-destructive">
                                  {step.error1}
                                </pre>
                              </div>
                            )}
                            {step.error2 && (
                              <div className="mt-1">
                                <span className="text-xs text-muted-foreground">执行 2:</span>
                                <pre className="mt-0.5 max-h-24 overflow-auto rounded bg-destructive/10 p-1.5 text-xs whitespace-pre-wrap break-all text-destructive">
                                  {step.error2}
                                </pre>
                              </div>
                            )}
                          </div>
                        ))}
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
})
