// 版本历史侧滑面板 - 展示工作流历史版本快照，支持查看快照详情与回滚
import { useState, useEffect } from 'react'
import { History, RotateCcw, ChevronRight, ChevronDown } from 'lucide-react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/Sheet'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { Skeleton } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { useToast } from '@/components/ui/Toast'
import { listVersions, restoreVersion } from '../services/api'
import { extractApiError } from '@/lib/utils'
import type { WorkflowVersion } from '../types/workflow'

interface Props {
  workflowId: string | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onRestored: () => void
}

export function VersionHistory({ workflowId, open, onOpenChange, onRestored }: Props) {
  const [versions, setVersions] = useState<WorkflowVersion[]>([])
  const [loading, setLoading] = useState(false)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [confirmVersion, setConfirmVersion] = useState<WorkflowVersion | null>(null)
  const [restoring, setRestoring] = useState(false)
  const toast = useToast()

  // 打开时加载版本列表
  useEffect(() => {
    if (!open || !workflowId) return
    let cancelled = false
    setLoading(true)
    setVersions([])
    listVersions(workflowId)
      .then((data) => {
        if (!cancelled) setVersions(data)
      })
      .catch((e) => {
        if (!cancelled) {
          toast.error(extractApiError(e) || '加载版本历史失败')
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, workflowId])

  const handleRestore = async () => {
    if (!workflowId || !confirmVersion) return
    setRestoring(true)
    try {
      await restoreVersion(workflowId, confirmVersion.id)
      toast.success(`已回滚到版本 ${confirmVersion.version_number}`)
      setConfirmVersion(null)
      onOpenChange(false)
      onRestored()
    } catch (e) {
      toast.error(extractApiError(e) || '回滚失败')
    } finally {
      setRestoring(false)
    }
  }

  // 时间转本地时区展示
  const formatTime = (iso: string) => {
    if (!iso) return ''
    try {
      return new Date(iso).toLocaleString()
    } catch {
      return iso
    }
  }

  // 提取步骤中的工具列表供快照摘要展示
  const getToolList = (v: WorkflowVersion): string[] => {
    return v.steps
      .filter((s) => s && typeof s === 'object' && 'tool' in s)
      .map((s) => s.tool)
      .filter((t): t is string => typeof t === 'string')
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-md flex flex-col gap-4 overflow-y-auto">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <History size={18} />
            版本历史
          </SheetTitle>
          <SheetDescription>查看历史版本并回滚到任意版本</SheetDescription>
        </SheetHeader>

        {loading ? (
          // 加载骨架
          <div className="flex flex-col gap-3" role="status" aria-busy="true">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-16 w-full" />
            ))}
          </div>
        ) : versions.length === 0 ? (
          // 空态
          <EmptyState
            icon={<History size={24} />}
            title="暂无版本历史"
            description="修改工作流后会自动创建版本快照"
          />
        ) : (
          <div className="flex flex-col gap-2">
            {versions.map((v) => {
              const isExpanded = expandedId === v.id
              const toolList = getToolList(v)
              return (
                <div
                  key={v.id}
                  className="rounded-md border border-border bg-card p-3"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex min-w-0 flex-1 flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <Badge variant="secondary">v{v.version_number}</Badge>
                        <span className="text-xs text-muted-foreground">
                          {formatTime(v.created_at)}
                        </span>
                      </div>
                      {v.note && (
                        <span className="text-xs text-muted-foreground">{v.note}</span>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setExpandedId(isExpanded ? null : v.id)}
                        aria-label={isExpanded ? '收起快照' : '查看快照'}
                        aria-expanded={isExpanded}
                      >
                        {isExpanded ? (
                          <ChevronDown size={14} />
                        ) : (
                          <ChevronRight size={14} />
                        )}
                        查看
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 px-2"
                        onClick={() => setConfirmVersion(v)}
                      >
                        <RotateCcw size={14} className="mr-1" />
                        回滚
                      </Button>
                    </div>
                  </div>
                  {isExpanded && (
                    <div className="mt-2 border-t border-border pt-2 text-xs text-muted-foreground">
                      <div>步骤数量：{v.steps.length}</div>
                      {toolList.length > 0 && (
                        <div className="mt-1 flex flex-wrap gap-1">
                          {toolList.map((t, i) => (
                            <Badge key={i} variant="outline" className="text-[10px]">
                              {t}
                            </Badge>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}

        {/* 回滚确认对话框 */}
        <ConfirmDialog
          open={confirmVersion !== null}
          title="确认回滚"
          message={
            confirmVersion
              ? `确认回滚到版本 ${confirmVersion.version_number}?当前状态会保存为新版本`
              : ''
          }
          danger
          confirmText={restoring ? '回滚中...' : '回滚'}
          onConfirm={handleRestore}
          onCancel={() => {
            if (!restoring) setConfirmVersion(null)
          }}
        />
      </SheetContent>
    </Sheet>
  )
}
