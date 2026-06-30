// 定时任务管理面板 - 展示已启用调度的工作流详情，支持禁用/立即执行
import { useState, useEffect, useRef } from 'react'
import type { ReactElement } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import {
  Clock,
  RefreshCw,
  Loader,
  X,
  Pause,
  Play,
  CircleCheck,
  CircleX,
  TriangleAlert,
} from 'lucide-react'
import {
  getScheduleStatus,
  runScheduleNow,
  disableSchedule,
  type ScheduleStatusItem,
} from '../services/api'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardFooter,
} from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { extractApiError } from '@/lib/utils'

interface Props {
  onClose: () => void
}

export function SchedulePanel({ onClose }: Props) {
  const [items, setItems] = useState<ScheduleStatusItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [running, setRunning] = useState<Record<string, boolean>>({})
  const refreshTimerRef = useRef<number | null>(null)
  const toast = useToast()

  const refresh = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const list = await getScheduleStatus()
      setItems(list)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载定时任务状态失败'
      setLoadError(msg)
      toast.error('加载定时任务状态失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  // 组件卸载时清理未触发的刷新定时器
  useEffect(() => {
    return () => {
      if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current)
    }
  }, [])

  const handleRunNow = async (workflowId: string, e: ReactMouseEvent) => {
    e.stopPropagation()
    setRunning((p) => ({ ...p, [workflowId]: true }))
    try {
      await runScheduleNow(workflowId)
      toast.success('已触发执行')
      // 触发后稍等再刷新，让 RunRecord 状态更新
      if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current)
      refreshTimerRef.current = window.setTimeout(() => refresh(), 800)
    } catch (e: unknown) {
      toast.error(extractApiError(e) || '触发执行失败')
    } finally {
      setRunning((p) => ({ ...p, [workflowId]: false }))
    }
  }

  const handleDisable = async (workflowId: string, e: ReactMouseEvent) => {
    e.stopPropagation()
    try {
      await disableSchedule(workflowId)
      toast.success('已禁用调度')
      refresh()
    } catch (e: unknown) {
      toast.error(extractApiError(e) || '禁用失败')
    }
  }

  const statusText = (s: string): ReactElement => {
    const map: Record<string, ReactElement> = {
      success: (
        <>
          <CircleCheck size={14} /> 成功
        </>
      ),
      failed: (
        <>
          <CircleX size={14} /> 失败
        </>
      ),
      partial_success: (
        <>
          <TriangleAlert size={14} /> 部分成功
        </>
      ),
      running: (
        <>
          <Loader size={14} className="animate-spin" /> 运行中
        </>
      ),
    }
    return map[s] || <>{s}</>
  }

  // 状态 Badge 变体映射：成功=success、失败=destructive、运行中=info+animate-pulse、部分成功=warning
  const statusBadgeVariant = (
    s: string
  ): 'success' | 'destructive' | 'info' | 'warning' | 'outline' => {
    if (s === 'success') return 'success'
    if (s === 'failed') return 'destructive'
    if (s === 'running') return 'info'
    if (s === 'partial_success') return 'warning'
    return 'outline'
  }

  const formatTime = (iso: string | null | undefined) => {
    if (!iso) return '-'
    try {
      const hasTz = iso.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(iso)
      const normalized = hasTz ? iso : iso + 'Z'
      return new Date(normalized).toLocaleString('zh-CN', { hour12: false })
    } catch {
      return iso.replace('T', ' ').slice(0, 19)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部工具条：刷新 / 关闭 */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">定时任务管理</h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={refresh}
            disabled={loading}
            title="刷新"
            aria-label="刷新定时任务列表"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title="关闭"
            aria-label="关闭定时任务面板"
          >
            <X size={16} />
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : loadError ? (
        <div className="flex flex-col items-center gap-2 py-8 text-center">
          <p className="text-sm text-destructive">{loadError}</p>
          <Button variant="outline" size="sm" onClick={refresh}>
            重试
          </Button>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Clock size={24} />}
          title="暂无定时任务"
          description="在工作流列表中启用调度即可生效"
        />
      ) : (
        <div className="flex flex-col gap-3">
          {items.map((item) => (
            <Card key={item.workflow_id}>
              <CardHeader className="pb-2">
                <div className="flex items-center justify-between gap-2">
                  <CardTitle className="text-sm">{item.name}</CardTitle>
                  <Badge variant="outline" className="font-mono gap-1" title="cron 表达式">
                    <Clock size={12} /> {item.cron || '未配置'}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 pb-2 text-sm">
                <div className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-muted-foreground">下次执行</span>
                  <span>{formatTime(item.next_run_time)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-muted-foreground">最近执行</span>
                  {item.last_run ? (
                    <span className="flex items-center gap-2">
                      <Badge
                        variant={statusBadgeVariant(item.last_run.status)}
                        className={
                          item.last_run.status === 'running'
                            ? 'animate-pulse gap-1'
                            : 'gap-1'
                        }
                      >
                        {statusText(item.last_run.status)}
                      </Badge>
                      <span className="text-muted-foreground">
                        {formatTime(item.last_run.started_at)}
                      </span>
                    </span>
                  ) : (
                    <span className="text-muted-foreground">暂无记录</span>
                  )}
                </div>
              </CardContent>
              <CardFooter className="gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={(e) => handleDisable(item.workflow_id, e)}
                  title="禁用调度"
                >
                  <Pause size={16} /> 禁用
                </Button>
                <Button
                  variant="default"
                  size="sm"
                  onClick={(e) => handleRunNow(item.workflow_id, e)}
                  disabled={running[item.workflow_id]}
                  title="立即执行一次"
                >
                  {running[item.workflow_id] ? (
                    <>
                      <Loader size={16} className="animate-spin" /> 执行中...
                    </>
                  ) : (
                    <>
                      <Play size={16} /> 立即执行
                    </>
                  )}
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}
