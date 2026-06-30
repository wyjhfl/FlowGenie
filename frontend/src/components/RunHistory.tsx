// 执行历史面板 - 展示某工作流的执行历史，支持展开详情、结构化展示与重试
// 重型渲染(步骤卡片/日志/对比 diff)已抽到 RunHistoryParts.tsx 并用 React.memo 优化
import { useState, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { getRunHistory, getRunDetail, retryRun, approveRun, getWorkflow, exportRunResult, exportWorkflowRuns, compareRuns, cleanupWorkflowRuns } from '../services/api'
import type { RetryRunResult, RunDiff } from '../services/api'
import type { WorkflowStep } from '../types/workflow'
import { useApprovalWebSocket } from '../hooks/useApprovalWebSocket'
import { History, RefreshCw, X, TriangleAlert, Download, GitCompare, Trash2 } from 'lucide-react'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { useToast } from '@/components/ui/Toast'
import { Card, CardHeader, CardContent } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/Tabs'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from '@/components/ui/DropdownMenu'
import { cn, extractApiError } from '@/lib/utils'
import {
  StepCards,
  RunLogs,
  RunDiffPanel,
  stepBadgeVariant,
  statusText,
  triggerText,
  formatLocalTime,
} from './RunHistoryParts'

interface RunListItem {
  id: string
  trigger_type: string
  status: string
  total_time_ms: number
  started_at: string
  finished_at: string | null
  error: string | null
}

interface RunDetail {
  id: string
  workflow_id: string
  trigger_type: string
  status: string
  total_time_ms: number
  steps_result: Record<string, unknown>
  started_at: string
  finished_at: string | null
  error: string | null
  logs: Array<{ timestamp: number; level: string; module: string; message: string }>
}

interface Props {
  workflowId: string
  onClose: () => void
  onSelectRun?: (runId: string) => void
}

export function RunHistory({ workflowId, onClose, onSelectRun }: Props) {
  const [runs, setRuns] = useState<RunListItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedRun, setSelectedRun] = useState<RunDetail | null>(null)
  const [expanded, setExpanded] = useState<string | null>(null)
  // 工作流步骤信息（用于步骤卡片展示名称与工具图标）
  const [stepMap, setStepMap] = useState<Record<string, WorkflowStep>>({})
  // 重试状态
  const [retryingRunId, setRetryingRunId] = useState<string | null>(null)
  const [retryError, setRetryError] = useState<string | null>(null)
  const [retryErrorRunId, setRetryErrorRunId] = useState<string | null>(null)
  // A1: 审批状态(记录正在审批的 run_id,用于按钮 loading)
  const [approvingRunId, setApprovingRunId] = useState<string | null>(null)
  // 导出状态(记录正在导出的 run_id,用于按钮 loading)
  const [exportingRunId, setExportingRunId] = useState<string | null>(null)
  // 导出全部执行记录(工作流维度)的 loading 状态
  const [exportingAll, setExportingAll] = useState(false)
  // 清理历史 loading 状态
  const [cleaning, setCleaning] = useState(false)
  // 步骤输出/错误展开状态
  const [expandedOutputs, setExpandedOutputs] = useState<Set<string>>(new Set())
  const [expandedErrors, setExpandedErrors] = useState<Set<string>>(new Set())
  // 日志区展开状态（按 run_id 维度）
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set())
  // 顶部状态筛选 Tab：全部/成功/失败/跳过
  const [statusFilter, setStatusFilter] = useState<'all' | 'success' | 'failed' | 'skipped'>('all')
  // 执行对比:选中的 run IDs(最多 2 条)
  const [compareIds, setCompareIds] = useState<string[]>([])
  // 对比 diff 结果
  const [diffResult, setDiffResult] = useState<RunDiff | null>(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)
  const toast = useToast()

  // 切换选中 run(最多 2 条,再次点击取消选中)
  const toggleCompare = (runId: string) => {
    setCompareIds((prev) => {
      if (prev.includes(runId)) {
        return prev.filter((id) => id !== runId)
      }
      if (prev.length >= 2) {
        // 已选 2 条时,替换最早选的
        return [prev[1], runId]
      }
      return [...prev, runId]
    })
    // 清空已有 diff 结果(选择变化后旧 diff 失效)
    setDiffResult(null)
    setDiffError(null)
  }

  // 执行对比
  const handleCompare = async () => {
    if (compareIds.length !== 2) return
    setDiffLoading(true)
    setDiffError(null)
    setDiffResult(null)
    try {
      const diff = await compareRuns(workflowId, compareIds[0], compareIds[1])
      setDiffResult(diff)
    } catch (err: unknown) {
      setDiffError(extractApiError(err) || '对比失败')
    } finally {
      setDiffLoading(false)
    }
  }

  // 关闭 diff 面板
  const closeDiff = () => {
    setDiffResult(null)
    setDiffError(null)
    setCompareIds([])
  }

  const refresh = async () => {
    setLoading(true)
    try {
      const list = await getRunHistory(workflowId)
      setRuns(list)
    } catch (e) {
      console.error('加载历史失败', e)
      toast.error('加载历史失败')
    } finally {
      setLoading(false)
    }
  }

  // A4: 订阅 WebSocket 审批事件,收到暂停/恢复时刷新历史列表
  useApprovalWebSocket({
    onPaused: () => { refresh() },
    onResumed: () => { refresh() },
  })

  // 加载工作流步骤信息（用于步骤卡片名称与工具图标）
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const wf = await getWorkflow(workflowId)
        if (cancelled) return
        const map: Record<string, WorkflowStep> = {}
        for (const s of wf.steps) map[s.id] = s
        setStepMap(map)
      } catch (e) {
        console.error('加载工作流步骤失败', e)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [workflowId])

  useEffect(() => {
    refresh()
  }, [workflowId])

  const handleExpand = async (runId: string) => {
    if (expanded === runId) {
      setExpanded(null)
      return
    }
    // 切换 run 时重置展开状态
    setExpandedOutputs(new Set())
    setExpandedErrors(new Set())
    setExpandedLogs(new Set())
    setRetryError(null)
    setRetryErrorRunId(null)
    try {
      const detail = await getRunDetail(workflowId, runId)
      setSelectedRun(detail)
      setExpanded(runId)
    } catch (e) {
      console.error('加载详情失败', e)
      toast.error('加载详情失败')
    }
  }

  const handleRetry = async (
    runId: string,
    mode: 'from_failed' | 'from_start',
    e?: React.MouseEvent
  ) => {
    e?.stopPropagation()
    if (retryingRunId) return
    setRetryError(null)
    setRetryErrorRunId(null)
    setRetryingRunId(runId)
    try {
      const newRun: RetryRunResult = await retryRun(workflowId, runId, mode)
      toast.success('重试已触发')
      // 刷新历史列表
      await refresh()
      // 自动展开新 run 详情
      try {
        const detail = await getRunDetail(workflowId, newRun.id)
        setSelectedRun(detail)
        setExpanded(newRun.id)
        setExpandedOutputs(new Set())
        setExpandedErrors(new Set())
        setExpandedLogs(new Set())
      } catch {
        // 详情加载失败不阻塞跳转
      }
      // 通知父组件（如需在主视图加载新 run）
      if (onSelectRun) onSelectRun(newRun.id)
    } catch (err: unknown) {
      setRetryError(extractApiError(err) || '重试失败')
      setRetryErrorRunId(runId)
    } finally {
      setRetryingRunId(null)
    }
  }

  // A1: 审批暂停的工作流(批准/拒绝),拒绝时弹窗输入理由
  const handleApprove = async (
    runId: string,
    decision: 'approved' | 'rejected',
    e?: React.MouseEvent
  ) => {
    e?.stopPropagation()
    if (approvingRunId) return
    let comment = ''
    if (decision === 'rejected') {
      comment = window.prompt('请输入拒绝理由(可选):') ?? ''
    }
    setApprovingRunId(runId)
    try {
      await approveRun(workflowId, runId, decision, comment)
      toast.success(decision === 'approved' ? '已批准,工作流继续执行' : '已拒绝,工作流已终止')
      await refresh()
    } catch (err: unknown) {
      toast.error(extractApiError(err) || '审批失败')
    } finally {
      setApprovingRunId(null)
    }
  }

  // 触发运行结果导出下载(json/csv/markdown)
  const handleExport = async (
    runId: string,
    format: 'json' | 'csv' | 'markdown',
    e?: React.MouseEvent
  ) => {
    e?.stopPropagation()
    if (exportingRunId) return
    setExportingRunId(runId)
    try {
      await exportRunResult(runId, format)
      toast.success('已开始下载')
    } catch (err: unknown) {
      toast.error(extractApiError(err) || '导出失败')
    } finally {
      setExportingRunId(null)
    }
  }

  // 导出当前工作流下的全部执行记录(CSV)
  const handleExportAll = async () => {
    if (exportingAll || runs.length === 0) return
    setExportingAll(true)
    try {
      await exportWorkflowRuns(workflowId, 'csv')
      toast.success('已开始下载')
    } catch (err: unknown) {
      toast.error(extractApiError(err) || '导出失败')
    } finally {
      setExportingAll(false)
    }
  }

  // 清理超期已完成执行记录(失败记录保留)
  const handleCleanup = async (
    retentionDays: number | undefined,
    e?: React.MouseEvent
  ) => {
    e?.stopPropagation()
    if (cleaning) return
    const hint =
      retentionDays === undefined
        ? '将按偏好保留天数清理超期的成功/跳过记录(失败记录保留),是否继续?'
        : retentionDays === 0
        ? 'retention=0 表示永久保留,不会清理任何记录。'
        : `将清理 ${retentionDays} 天前的成功/跳过记录(失败记录保留),是否继续?`
    if (!window.confirm(hint)) return
    setCleaning(true)
    try {
      const result = await cleanupWorkflowRuns(
        workflowId,
        retentionDays !== undefined ? { retentionDays } : undefined
      )
      toast.success(`已清理 ${result.deleted} 条超期记录`)
      await refresh()
    } catch (err: unknown) {
      toast.error(extractApiError(err) || '清理失败')
    } finally {
      setCleaning(false)
    }
  }

  const toggleOutput = useCallback((key: string) => {
    setExpandedOutputs((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleError = useCallback((key: string) => {
    setExpandedErrors((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const toggleLogs = useCallback((runId: string) => {
    setExpandedLogs((prev) => {
      const next = new Set(prev)
      if (next.has(runId)) next.delete(runId)
      else next.add(runId)
      return next
    })
  }, [])

  // 状态筛选：将 run 状态映射到筛选 Tab（partial_success 归入"跳过"）
  const filterRunByStatus = (status: string): boolean => {
    if (statusFilter === 'all') return true
    if (statusFilter === 'success') return status === 'success'
    if (statusFilter === 'failed') return status === 'failed'
    if (statusFilter === 'skipped') return status === 'partial_success'
    return true
  }

  const statusFilterTabs: Array<{ key: 'all' | 'success' | 'failed' | 'skipped'; label: string }> = [
    { key: 'all', label: '全部' },
    { key: 'success', label: '成功' },
    { key: 'failed', label: '失败' },
    { key: 'skipped', label: '跳过' },
  ]

  const filteredRuns = runs.filter((r) => filterRunByStatus(r.status))

  // 各状态筛选 Tab 的计数（全部 / 成功 / 失败 / 跳过=partial_success）
  const countForStatus = (key: 'all' | 'success' | 'failed' | 'skipped'): number => {
    if (key === 'all') return runs.length
    if (key === 'success') return runs.filter((r) => r.status === 'success').length
    if (key === 'failed') return runs.filter((r) => r.status === 'failed').length
    return runs.filter((r) => r.status === 'partial_success').length
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-border p-3">
        <h3 className="text-base font-semibold">执行历史</h3>
        <div className="flex items-center gap-1">
          {compareIds.length === 2 && (
            <Button
              variant="default"
              size="sm"
              className="h-7 gap-1"
              onClick={handleCompare}
              disabled={diffLoading}
            >
              <GitCompare size={14} />
              {diffLoading ? '对比中...' : '对比'}
            </Button>
          )}
          {compareIds.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs"
              onClick={() => setCompareIds([])}
            >
              清除选择({compareIds.length}/2)
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            className="h-7 gap-1"
            onClick={handleExportAll}
            disabled={exportingAll || loading || runs.length === 0}
            title="导出当前工作流的全部执行记录为 CSV"
          >
            <Download size={14} className={cn(exportingAll && 'animate-pulse')} />
            {exportingAll ? '导出中...' : '导出全部'}
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 gap-1"
                disabled={cleaning || loading || runs.length === 0}
                title="清理超期已完成执行记录(失败记录保留)"
              >
                <Trash2 size={14} className={cn(cleaning && 'animate-pulse')} />
                {cleaning ? '清理中...' : '清理 ▾'}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem
                disabled={cleaning}
                onClick={(e) => handleCleanup(undefined, e)}
              >
                按偏好保留天数清理
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={cleaning}
                onClick={(e) => handleCleanup(30, e)}
              >
                清理 30 天前的记录
              </DropdownMenuItem>
              <DropdownMenuItem
                disabled={cleaning}
                onClick={(e) => handleCleanup(7, e)}
              >
                清理 7 天前的记录
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={refresh} disabled={loading}>
            <RefreshCw size={14} className={cn(loading && 'animate-spin')} />
          </Button>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
            <X size={14} />
          </Button>
        </div>
      </div>
      {/* 状态筛选 Tab：全部 / 成功 / 失败 / 跳过 */}
      {!loading && runs.length > 0 && (
        <div className="px-3 pt-3">
          <Tabs value={statusFilter} onValueChange={(v) => setStatusFilter(v as typeof statusFilter)}>
            <TabsList className="w-full">
              {statusFilterTabs.map((tab) => (
                <TabsTrigger key={tab.key} value={tab.key} className="flex-1">
                  {tab.label} ({countForStatus(tab.key)})
                </TabsTrigger>
              ))}
            </TabsList>
          </Tabs>
        </div>
      )}
      {loading ? (
        <div className="flex flex-col gap-2 p-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : runs.length === 0 ? (
        <div className="flex-1 p-3">
          <EmptyState
            icon={<History size={24} />}
            title="暂无执行记录"
            description="执行工作流后将在此查看历史"
          />
        </div>
      ) : filteredRuns.length === 0 ? (
        <p className="p-3 text-sm text-muted-foreground">无匹配的执行记录</p>
      ) : (
        <div className="flex-1 flex flex-col gap-2 overflow-y-auto p-3">
          <AnimatePresence mode="popLayout">
          {filteredRuns.map((run) => {
            const isRetrying = retryingRunId === run.id
            const canRetry = run.status === 'failed' || run.status === 'partial_success'
            const canApprove = run.status === 'paused'
            const isApproving = approvingRunId === run.id
            const isExpanded = expanded === run.id && selectedRun && selectedRun.id === run.id
            return (
              <motion.div
                key={run.id}
                layout
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.9 }}
                transition={{ type: 'spring', stiffness: 300, damping: 30 }}
              >
              <Card
                className={cn(
                  'cursor-pointer transition-colors hover:bg-accent/40',
                  expanded === run.id && 'ring-1 ring-primary',
                  compareIds.includes(run.id) && 'ring-1 ring-warning'
                )}
                onClick={() => handleExpand(run.id)}
                role="button"
                aria-expanded={!!isExpanded}
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault()
                    handleExpand(run.id)
                  }
                }}
              >
                <CardHeader className="p-3 pb-2 space-y-0">
                  <div className="flex flex-wrap items-center gap-2">
                    {/* 对比选择 checkbox(最多选 2 条) */}
                    <input
                      type="checkbox"
                      className="h-4 w-4 shrink-0 cursor-pointer rounded border-border accent-warning"
                      checked={compareIds.includes(run.id)}
                      disabled={compareIds.length >= 2 && !compareIds.includes(run.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => {
                        e.stopPropagation()
                        toggleCompare(run.id)
                      }}
                      aria-label="选择此执行进行对比"
                    />
                    <Badge
                      variant={stepBadgeVariant(run.status)}
                      className={cn(run.status === 'running' && 'animate-pulse')}
                    >
                      {statusText(run.status)}
                    </Badge>
                    <span className="text-xs text-muted-foreground">{triggerText(run.trigger_type)}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {formatLocalTime(run.started_at)}
                    </span>
                    <span className="text-xs text-muted-foreground">{run.total_time_ms}ms</span>
                    {canRetry && (
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7"
                            disabled={!!retryingRunId}
                            onClick={(e) => e.stopPropagation()}
                          >
                            {isRetrying ? '重试中...' : '重试 ▾'}
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent
                          align="end"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <DropdownMenuItem
                            disabled={!!retryingRunId}
                            onClick={(e) => handleRetry(run.id, 'from_failed', e)}
                          >
                            从失败步骤重试
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            disabled={!!retryingRunId}
                            onClick={(e) => handleRetry(run.id, 'from_start', e)}
                          >
                            从头重试
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    )}
                    {canApprove && (
                      <div className="flex items-center gap-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 border-success text-success hover:bg-success/10"
                          disabled={!!approvingRunId}
                          onClick={(e) => handleApprove(run.id, 'approved', e)}
                        >
                          {isApproving ? '处理中...' : '批准'}
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-7 border-destructive text-destructive hover:bg-destructive/10"
                          disabled={!!approvingRunId}
                          onClick={(e) => handleApprove(run.id, 'rejected', e)}
                        >
                          拒绝
                        </Button>
                      </div>
                    )}
                  </div>
                </CardHeader>
                {retryError && retryErrorRunId === run.id && (
                  <div className="px-3 pb-1 text-xs text-destructive"><TriangleAlert className="inline h-3 w-3" /> {retryError}</div>
                )}
                {/* 步骤详情容器：motion.div height auto 动画（替代原 grid-rows 过渡）
                    内容仅在 selectedRun 已加载且匹配当前 run 时渲染（保持原数据懒加载逻辑） */}
                <motion.div
                  initial={{ height: 0 }}
                  animate={{ height: isExpanded ? 'auto' : 0 }}
                  exit={{ height: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <CardContent className="p-3 pt-0">
                    {selectedRun && selectedRun.id === run.id && (
                      <>
                        {run.error && (
                          <div className="mb-2 text-xs text-destructive">错误: {run.error}</div>
                        )}
                        {/* 导出按钮:展开后显示,支持 JSON/CSV/Markdown 三种格式 */}
                        <div className="mb-2 flex justify-end">
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7"
                                disabled={exportingRunId === run.id}
                                onClick={(e) => e.stopPropagation()}
                              >
                                <Download size={14} className="mr-1" />
                                {exportingRunId === run.id ? '导出中...' : '导出 ▾'}
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent
                              align="end"
                              onClick={(e) => e.stopPropagation()}
                            >
                              <DropdownMenuItem
                                disabled={!!exportingRunId}
                                onClick={(e) => handleExport(run.id, 'json', e)}
                              >
                                JSON
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                disabled={!!exportingRunId}
                                onClick={(e) => handleExport(run.id, 'csv', e)}
                              >
                                CSV
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                disabled={!!exportingRunId}
                                onClick={(e) => handleExport(run.id, 'markdown', e)}
                              >
                                Markdown
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                        <StepCards
                          stepsResult={selectedRun.steps_result}
                          stepMap={stepMap}
                          runId={selectedRun.id}
                          expandedOutputs={expandedOutputs}
                          expandedErrors={expandedErrors}
                          onToggleOutput={toggleOutput}
                          onToggleError={toggleError}
                        />
                        <RunLogs
                          runId={run.id}
                          logs={selectedRun.logs}
                          isExpanded={expandedLogs.has(run.id)}
                          onToggle={toggleLogs}
                        />
                      </>
                    )}
                  </CardContent>
                </motion.div>
              </Card>
              </motion.div>
            )
          })}
          </AnimatePresence>
        </div>
      )}
      {/* 执行对比 diff 面板(选中 2 条 run 后点击对比按钮触发) */}
      <RunDiffPanel
        diffResult={diffResult}
        diffLoading={diffLoading}
        diffError={diffError}
        onClose={closeDiff}
      />
    </div>
  )
}
