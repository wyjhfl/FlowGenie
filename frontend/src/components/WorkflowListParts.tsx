// WorkflowList 子组件(从 WorkflowList.tsx 抽出)
// - WorkflowCard: 单个工作流卡片(含编辑态/标签/状态徽标/更多操作菜单/Webhook 展示)
// - BatchToolbar: 批量操作工具栏(选中时显示)
// 均用 React.memo 包裹,避免父组件无关状态变更(如搜索框输入)触发全量列表重渲染。
import { memo, useState, useEffect } from 'react'
import type { KeyboardEvent, FocusEvent } from 'react'
import { motion } from 'framer-motion'
import {
  Clock,
  Webhook,
  Copy,
  Pencil,
  Pause,
  Play,
  Trash2,
  MoreVertical,
  History,
  X,
  Link2,
} from 'lucide-react'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/Select'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/DropdownMenu'
import { Tooltip, TooltipTrigger, TooltipContent } from '@/components/ui/Tooltip'
import { useToast } from '@/components/ui/Toast'
import { getWorkflow, listWorkflows, updateWorkflow } from '../services/api'
import { cn } from '@/lib/utils'

// ===== 共享类型 =====

export interface WorkflowCardItem {
  id: string
  name: string
  scenario: string
  schedule_enabled: boolean
  webhook_id: string | null
  triggers: string[]
  tags: string[]
  created_at: string
  updated_at: string
}

export type BatchAction = 'enable_schedule' | 'disable_schedule' | 'delete'

// ===== ChainTriggerDialog(A3: 完成后链式触发配置弹窗) =====

interface ChainTriggerDialogProps {
  open: boolean
  wfId: string
  wfName: string
  onClose: () => void
}

/** A3: 链式触发配置弹窗——选择目标工作流 + 触发条件(success/failed/always)
 *
 * 打开时调用 getWorkflow 加载当前 on_complete_trigger,listWorkflows 加载可选目标。
 * 保存时调用 updateWorkflow 持久化。深度上限由后端 _chain_depth 运行时控制。
 */
function ChainTriggerDialog({ open, wfId, wfName, onClose }: ChainTriggerDialogProps) {
  const toast = useToast()
  const [workflowList, setWorkflowList] = useState<Array<{ id: string; name: string }>>([])
  const [selected, setSelected] = useState<Record<string, string>>({}) // { targetWfId: on }
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    Promise.all([listWorkflows(), getWorkflow(wfId)])
      .then(([list, detail]) => {
        if (cancelled) return
        setWorkflowList(list.map((w) => ({ id: w.id, name: w.name })))
        const map: Record<string, string> = {}
        for (const t of detail.on_complete_trigger || []) {
          if (t.workflow_id && t.on) map[t.workflow_id] = t.on
        }
        setSelected(map)
      })
      .catch(() => {
        if (cancelled) return
        toast.error('加载工作流列表失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, wfId])

  const handleToggle = (targetId: string, checked: boolean) => {
    setSelected((prev) => {
      const next = { ...prev }
      if (checked) {
        next[targetId] = prev[targetId] || 'always'
      } else {
        delete next[targetId]
      }
      return next
    })
  }

  const handleOnChange = (targetId: string, onVal: string) => {
    setSelected((prev) => ({ ...prev, [targetId]: onVal }))
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const triggers = Object.entries(selected).map(([workflow_id, on]) => ({
        workflow_id,
        on,
      }))
      await updateWorkflow(wfId, { on_complete_trigger: triggers })
      toast.success('链式触发配置已保存')
      onClose()
    } catch {
      toast.error('保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 排除自身(不能链式触发自己,后端 validator 也会拦截)
  const available = workflowList.filter((w) => w.id !== wfId)

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[80vh] max-w-md overflow-y-auto">
        <DialogHeader>
          <DialogTitle>完成后触发配置</DialogTitle>
          <DialogDescription>
            配置「{wfName}」执行完成后自动触发的目标工作流。链式嵌套深度上限 3 层。
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <p className="py-4 text-center text-sm text-muted-foreground">加载中...</p>
        ) : available.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            暂无其他工作流可选。请先创建目标工作流。
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {available.map((w) => {
              const checked = !!selected[w.id]
              return (
                <div
                  key={w.id}
                  className="flex items-center gap-2 rounded-md border border-border p-2"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={(e) => handleToggle(w.id, e.target.checked)}
                    className="h-4 w-4 shrink-0 cursor-pointer rounded border-border"
                    aria-label={`选择工作流 ${w.name}`}
                  />
                  <span className="min-w-0 flex-1 truncate text-sm">{w.name}</span>
                  {checked && (
                    <Select
                      value={selected[w.id]}
                      onValueChange={(v) => handleOnChange(w.id, v)}
                    >
                      <SelectTrigger className="h-8 w-28 text-xs">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="always">总是触发</SelectItem>
                        <SelectItem value="success">成功时</SelectItem>
                        <SelectItem value="failed">失败时</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )
            })}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={saving}>
            取消
          </Button>
          <Button size="sm" onClick={handleSave} disabled={saving || loading}>
            {saving ? '保存中...' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}


// ===== WorkflowCard =====

interface WorkflowCardProps {
  wf: WorkflowCardItem
  isActive: boolean
  isSelected: boolean
  isEditing: boolean
  isActionLoading: boolean
  editingName: string
  editingTags: string[]
  tagInput: string
  webhookUrl: string | null
  onLoad: (id: string) => void
  onToggleSelect: (id: string) => void
  onStartRename: (wf: WorkflowCardItem) => void
  onRenameKeyDown: (e: KeyboardEvent<HTMLInputElement>, id: string) => void
  onRenameBlur: (e: FocusEvent<HTMLInputElement>, id: string) => void
  onEditingNameChange: (val: string) => void
  onRemoveEditingTag: (tag: string) => void
  onTagInputChange: (val: string) => void
  onTagInputKeyDown: (e: KeyboardEvent<HTMLInputElement>) => void
  onDuplicate: (id: string) => void
  onToggleSchedule: (id: string, enabled: boolean) => void
  onOpenVersionHistory: (id: string) => void
  onDelete: (id: string) => void
  onCopyWebhook: (url: string) => void
}

export const WorkflowCard = memo(function WorkflowCard({
  wf,
  isActive,
  isSelected,
  isEditing,
  isActionLoading,
  editingName,
  editingTags,
  tagInput,
  webhookUrl,
  onLoad,
  onToggleSelect,
  onStartRename,
  onRenameKeyDown,
  onRenameBlur,
  onEditingNameChange,
  onRemoveEditingTag,
  onTagInputChange,
  onTagInputKeyDown,
  onDuplicate,
  onToggleSchedule,
  onOpenVersionHistory,
  onDelete,
  onCopyWebhook,
}: WorkflowCardProps) {
  // A3: 链式触发配置弹窗 state(内部管理,不污染父组件)
  const [showChain, setShowChain] = useState(false)
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ type: 'spring', stiffness: 300, damping: 30 }}
      whileHover={{ scale: 1.02, y: -2 }}
    >
      <Card
        className={cn(
          'cursor-pointer transition-all duration-200 hover:bg-accent/50 hover:border-primary/40 hover:shadow-lg hover:-translate-y-0.5',
          isActive && 'border-primary ring-2 ring-primary'
        )}
        onClick={() => onLoad(wf.id)}
        role="button"
        aria-expanded={false}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onLoad(wf.id)
          }
        }}
      >
        {/* CardHeader:checkbox + 标题 + 标签 + 状态 Badge + DropdownMenu 更多操作 */}
        <CardHeader className="flex-row items-start justify-between space-y-0 p-4 pb-2">
          <div className="flex items-start gap-2 min-w-0 flex-1">
            {/* 选择 checkbox */}
            <input
              type="checkbox"
              checked={isSelected}
              onChange={() => onToggleSelect(wf.id)}
              onClick={(e) => e.stopPropagation()}
              className="mt-1 h-4 w-4 shrink-0 cursor-pointer rounded border-border"
              aria-label={`选择工作流 ${wf.name}`}
            />
            <div className="flex min-w-0 flex-1 flex-col gap-1" data-editing-area="true">
              {isEditing ? (
                <>
                  <Input
                    value={editingName}
                    autoFocus
                    className="h-8"
                    onClick={(e) => e.stopPropagation()}
                    onChange={(e) => onEditingNameChange(e.target.value)}
                    onKeyDown={(e) => onRenameKeyDown(e, wf.id)}
                    onBlur={(e) => onRenameBlur(e, wf.id)}
                  />
                  {/* 标签编辑:回车添加,点击 x 删除 */}
                  <div className="flex flex-wrap items-center gap-1">
                    {editingTags.map((tag) => (
                      <Badge
                        key={tag}
                        variant="secondary"
                        className="gap-1 text-[10px]"
                      >
                        {tag}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation()
                            onRemoveEditingTag(tag)
                          }}
                          className="text-muted-foreground hover:text-destructive"
                          aria-label={`删除标签 ${tag}`}
                        >
                          <X size={10} />
                        </button>
                      </Badge>
                    ))}
                    <input
                      type="text"
                      value={tagInput}
                      placeholder="添加标签..."
                      className="h-6 w-20 rounded border border-input bg-background px-1 text-xs"
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) => onTagInputChange(e.target.value)}
                      onKeyDown={onTagInputKeyDown}
                    />
                  </div>
                </>
              ) : (
                <CardTitle
                  className="truncate text-sm font-medium"
                  title="双击重命名"
                  onDoubleClick={(e) => {
                    e.stopPropagation()
                    onStartRename(wf)
                  }}
                >
                  {wf.name}
                </CardTitle>
              )}
              {wf.scenario && (
                <CardDescription className="truncate text-xs">
                  {wf.scenario}
                </CardDescription>
              )}
              {/* 标签展示(非编辑态) */}
              {!isEditing && wf.tags && wf.tags.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {wf.tags.map((tag) => (
                    <Badge key={tag} variant="secondary" className="text-[10px]">
                      {tag}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {/* 状态色条改用 Badge 变体:schedule=secondary、webhook=default */}
            {wf.schedule_enabled && (
              <Badge variant="secondary" className="gap-1">
                <Clock size={12} />
                调度
              </Badge>
            )}
            {wf.webhook_id && (
              <Badge variant="default" className="gap-1">
                <Webhook size={12} />
                Webhook
              </Badge>
            )}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7"
                  onClick={(e) => e.stopPropagation()}
                  aria-label="更多操作"
                >
                  <MoreVertical size={14} />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => onStartRename(wf)}
                  disabled={isEditing || isActionLoading}
                >
                  <Pencil size={14} className="mr-2" />
                  重命名
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => onDuplicate(wf.id)}
                  disabled={isActionLoading}
                >
                  <Copy size={14} className="mr-2" />
                  复制工作流
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => onToggleSchedule(wf.id, wf.schedule_enabled)}
                  disabled={isActionLoading}
                >
                  {wf.schedule_enabled ? (
                    <>
                      <Pause size={14} className="mr-2" />
                      禁用调度
                    </>
                  ) : (
                    <>
                      <Play size={14} className="mr-2" />
                      启用调度
                    </>
                  )}
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => onOpenVersionHistory(wf.id)}>
                  <History size={14} className="mr-2" />
                  版本历史
                </DropdownMenuItem>
                {/* A3: 链式触发配置——完成后自动触发目标工作流 */}
                <DropdownMenuItem
                  onSelect={(e) => {
                    e.preventDefault()
                    setShowChain(true)
                  }}
                  disabled={isActionLoading}
                >
                  <Link2 size={14} className="mr-2" />
                  完成后触发
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive focus:text-destructive"
                  onSelect={() => onDelete(wf.id)}
                >
                  <Trash2 size={14} className="mr-2" />
                  删除
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </CardHeader>

        {/* CardContent:webhook code 块 + 复制按钮(ghost size=icon + Tooltip) */}
        {webhookUrl && (
          <CardContent className="flex flex-col gap-2 p-4 pt-0">
            <div className="flex items-center gap-2">
              <code
                className="min-w-0 flex-1 truncate rounded bg-muted px-2 py-1 font-mono text-xs text-muted-foreground"
                title={webhookUrl}
                onClick={(e) => {
                  e.stopPropagation()
                  onCopyWebhook(webhookUrl)
                }}
              >
                {webhookUrl}
              </code>
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-7 w-7 shrink-0"
                    aria-label="复制 Webhook URL"
                    onClick={(e) => {
                      e.stopPropagation()
                      onCopyWebhook(webhookUrl)
                    }}
                  >
                    <Copy size={14} />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>复制 Webhook URL</TooltipContent>
              </Tooltip>
            </div>
          </CardContent>
        )}

        {/* CardFooter:更新时间 */}
        {wf.updated_at && (
          <CardFooter className="justify-between p-4 pt-0 text-xs text-muted-foreground">
            <span>更新于 {wf.updated_at?.slice(0, 10)}</span>
          </CardFooter>
        )}
      </Card>
      {/* A3: 链式触发配置弹窗(条件渲染——仅 showChain=true 时挂载,避免未使用时执行 useToast) */}
      {showChain && (
        <ChainTriggerDialog
          open={showChain}
          wfId={wf.id}
          wfName={wf.name}
          onClose={() => setShowChain(false)}
        />
      )}
    </motion.div>
  )
})

// ===== BatchToolbar =====

interface BatchToolbarProps {
  selectedCount: number
  batchLoading: boolean
  onBatchAction: (action: BatchAction) => void
  onBatchDelete: () => void
  onClearSelection: () => void
}

export const BatchToolbar = memo(function BatchToolbar({
  selectedCount,
  batchLoading,
  onBatchAction,
  onBatchDelete,
  onClearSelection,
}: BatchToolbarProps) {
  if (selectedCount === 0) return null
  return (
    <div className="flex items-center gap-2 rounded-md border border-primary/30 bg-primary/5 p-2">
      <span className="text-xs font-medium text-foreground">
        已选 {selectedCount} 项
      </span>
      <div className="flex-1" />
      <Button
        variant="outline"
        size="sm"
        className="h-7"
        onClick={() => onBatchAction('enable_schedule')}
        disabled={batchLoading}
      >
        <Play size={14} className="mr-1" />
        启用调度
      </Button>
      <Button
        variant="outline"
        size="sm"
        className="h-7"
        onClick={() => onBatchAction('disable_schedule')}
        disabled={batchLoading}
      >
        <Pause size={14} className="mr-1" />
        禁用调度
      </Button>
      <Button
        variant="destructive"
        size="sm"
        className="h-7"
        onClick={onBatchDelete}
        disabled={batchLoading}
      >
        <Trash2 size={14} className="mr-1" />
        批量删除
      </Button>
      <Button
        variant="ghost"
        size="sm"
        className="h-7"
        onClick={onClearSelection}
        disabled={batchLoading}
        aria-label="取消选择"
      >
        取消
      </Button>
    </div>
  )
})
