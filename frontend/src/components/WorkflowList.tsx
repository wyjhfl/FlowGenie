// 工作流列表侧栏 - 展示已保存工作流，支持加载/删除/调度切换/导入/复制/重命名/搜索筛选
// 重型渲染(单卡片/批量工具栏)已抽到 WorkflowListParts.tsx 并用 React.memo 优化
import { useState, useEffect, useRef, useCallback, forwardRef, useImperativeHandle } from 'react'
import type { ChangeEvent, KeyboardEvent, FocusEvent } from 'react'
import { AnimatePresence } from 'framer-motion'
import {
  Download,
  RefreshCw,
  Loader,
  Inbox,
  Search,
  Tag,
  X,
} from 'lucide-react'
import {
  deleteWorkflow,
  enableSchedule,
  disableSchedule,
  importWorkflow,
  duplicateWorkflow,
  updateWorkflowWithTags,
  batchWorkflows,
  listWorkflowsByTags,
} from '../services/api'
import { VersionHistory } from './VersionHistory'
import { WorkflowCard, BatchToolbar, type WorkflowCardItem, type BatchAction } from './WorkflowListParts'
import { Card, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
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
import { Tooltip, TooltipTrigger, TooltipContent, TooltipProvider } from '@/components/ui/Tooltip'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { useToast } from '@/components/ui/Toast'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { extractApiError } from '@/lib/utils'

// API 基础地址（与 services/api.ts 保持一致：优先环境变量，缺省走同源）
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

// 非编辑卡片传入的常量,避免每次渲染创建新引用破坏 React.memo
const EMPTY_TAGS: string[] = []

type WorkflowListItem = WorkflowCardItem

type FilterTrigger = 'all' | 'manual' | 'schedule' | 'webhook'

interface Props {
  currentWorkflowId: string | null
  onLoad: (id: string) => void
  onRefresh: (deletedId?: string) => void
}

export interface WorkflowListHandle {
  refresh: () => Promise<void>
}

export const WorkflowList = forwardRef<WorkflowListHandle, Props>(function WorkflowList(
  { currentWorkflowId, onLoad, onRefresh },
  ref
) {
  const [workflows, setWorkflows] = useState<WorkflowListItem[]>([])
  const [loading, setLoading] = useState(false)
  const toast = useToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [filterTrigger, setFilterTrigger] = useState<FilterTrigger>('all')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editingName, setEditingName] = useState('')
  // 确认对话框状态（替代原生 confirm：open 控制显隐，message 为提示文案，onConfirm 为确认回调）
  const [confirmState, setConfirmState] = useState<{
    open: boolean
    message: string
    onConfirm: () => void
  }>({ open: false, message: '', onConfirm: () => {} })
  // 列表加载错误信息（非空时展示错误态 + 重试按钮）
  const [loadError, setLoadError] = useState('')
  // 操作防重：用 workflow id 标记当前正在执行的卡片操作（重命名/复制/调度切换）
  const [actionLoading, setActionLoading] = useState<string>('')
  // 批量选择：用 Set 收集选中工作流 id
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  // 批量操作进行中（禁用按钮）
  const [batchLoading, setBatchLoading] = useState(false)
  // 标签筛选：选中的标签集合（工作流需全部包含）
  const [tagFilter, setTagFilter] = useState<Set<string>>(new Set())
  // 重命名模式下编辑的标签列表 + 标签输入框值
  const [editingTags, setEditingTags] = useState<string[]>([])
  const [tagInput, setTagInput] = useState('')
  // 版本历史 Sheet 状态
  const [versionHistoryId, setVersionHistoryId] = useState<string | null>(null)
  const [versionHistoryOpen, setVersionHistoryOpen] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true)
    setLoadError('')
    try {
      const list = await listWorkflowsByTags([])
      setWorkflows(list)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载工作流列表失败'
      setLoadError(msg)
      toast.error('加载工作流列表失败')
    } finally {
      setLoading(false)
    }
  }, [toast])

  useEffect(() => {
    refresh()
  }, [refresh])

  useImperativeHandle(ref, () => ({
    refresh,
  }))

  // 收集所有工作流的标签去重排序，供标签筛选下拉使用
  const allTags = Array.from(
    new Set(workflows.flatMap((wf) => wf.tags || []))
  ).sort()

  // 搜索 + 触发类型 + 标签筛选（纯前端）
  const filteredWorkflows = workflows.filter((wf) => {
    if (searchQuery && !wf.name.toLowerCase().includes(searchQuery.toLowerCase())) {
      return false
    }
    if (filterTrigger !== 'all') {
      const triggerToolMap: Record<Exclude<FilterTrigger, 'all'>, string> = {
        manual: 'manual_trigger',
        schedule: 'schedule_trigger',
        webhook: 'webhook_trigger',
      }
      const targetTool = triggerToolMap[filterTrigger]
      if (!wf.triggers || !wf.triggers.includes(targetTool)) {
        return false
      }
    }
    // 标签筛选：工作流需包含所有选中的筛选标签
    if (tagFilter.size > 0) {
      const wfTags = wf.tags || []
      for (const t of tagFilter) {
        if (!wfTags.includes(t)) return false
      }
    }
    return true
  })

  const handleDelete = useCallback((id: string) => {
    // 替代原生 confirm：弹出 ConfirmDialog，确认后执行删除
    setConfirmState({
      open: true,
      message: '确认删除此工作流及其所有执行历史？',
      onConfirm: async () => {
        try {
          await deleteWorkflow(id)
          toast.success('已删除')
          refresh()
          onRefresh(id)
        } catch {
          toast.error('删除失败')
        }
        setConfirmState((s) => ({ ...s, open: false }))
      },
    })
  }, [refresh, onRefresh, toast])

  const handleToggleSchedule = useCallback(async (id: string, enabled: boolean) => {
    if (actionLoading) return
    setActionLoading(id)
    try {
      if (enabled) {
        await disableSchedule(id)
      } else {
        await enableSchedule(id)
      }
      toast.success(enabled ? '已禁用调度' : '已启用调度')
      refresh()
    } catch (e: unknown) {
      toast.error(extractApiError(e) || '操作失败')
    } finally {
      setActionLoading('')
    }
  }, [actionLoading, refresh, toast])

  const handleCopyWebhook = useCallback(async (url: string) => {
    try {
      await navigator.clipboard.writeText(url)
      toast.success('已复制 Webhook URL')
    } catch {
      toast.error('复制失败，请手动复制')
    }
  }, [toast])

  const handleImportClick = () => {
    fileInputRef.current?.click()
  }

  const handleFileChange = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const text = await file.text()
      const data = JSON.parse(text)
      const payload = {
        name: typeof data.name === 'string' && data.name ? data.name : file.name.replace(/\.json$/i, ''),
        steps: Array.isArray(data.steps) ? data.steps : [],
        edges: Array.isArray(data.edges) ? data.edges : [],
        scenario: typeof data.scenario === 'string' ? data.scenario : '',
        summary: typeof data.summary === 'string' ? data.summary : '',
        on_failure: typeof data.on_failure === 'string' ? data.on_failure : 'stop',
      }
      await importWorkflow(payload)
      toast.success('导入成功')
      await refresh()
      onRefresh()
    } catch (err: unknown) {
      const msg = extractApiError(err) || '导入失败：文件格式无效'
      toast.error(msg)
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleDuplicate = useCallback(async (id: string) => {
    if (actionLoading) return
    setActionLoading(id)
    try {
      await duplicateWorkflow(id)
      toast.success('已复制')
      await refresh()
      onRefresh()
    } catch (err: unknown) {
      const msg = extractApiError(err) || '复制失败'
      toast.error(msg)
    } finally {
      setActionLoading('')
    }
  }, [actionLoading, refresh, onRefresh, toast])

  const handleStartRename = useCallback((wf: WorkflowListItem) => {
    setEditingId(wf.id)
    setEditingName(wf.name)
    setEditingTags([...(wf.tags || [])])
    setTagInput('')
  }, [])

  const handleRenameSubmit = useCallback(async (id: string) => {
    const trimmed = editingName.trim()
    if (!trimmed) {
      toast.error('名称不能为空')
      return // 保持编辑态
    }
    if (actionLoading) return
    setActionLoading(id)
    try {
      await updateWorkflowWithTags(id, { name: trimmed, tags: editingTags })
      setEditingId(null)
      setEditingName('')
      setEditingTags([])
      setTagInput('')
      toast.success('已保存')
      await refresh()
      onRefresh()
    } catch (err: unknown) {
      const msg = extractApiError(err) || '重命名失败'
      toast.error(msg)
    } finally {
      setActionLoading('')
    }
  }, [editingName, editingTags, actionLoading, refresh, onRefresh, toast])

  const handleRenameCancel = useCallback(() => {
    setEditingId(null)
    setEditingName('')
    setEditingTags([])
    setTagInput('')
  }, [])

  // 标签编辑：回车添加标签
  const addEditingTag = useCallback(() => {
    const t = tagInput.trim()
    if (t && !editingTags.includes(t)) {
      setEditingTags([...editingTags, t])
    }
    setTagInput('')
  }, [tagInput, editingTags])

  // 标签编辑：移除标签
  const removeEditingTag = useCallback((tag: string) => {
    setEditingTags((prev) => prev.filter((t) => t !== tag))
  }, [])

  // 标签输入框 Enter 添加(供 WorkflowCard 的 tagInput onKeyDown 使用)
  const handleTagInputKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addEditingTag()
    }
  }, [addEditingTag])

  // 批量选择：切换选中状态
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // 标签筛选：切换标签选中
  const toggleTagFilter = (tag: string) => {
    setTagFilter((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })
  }

  // 批量操作
  const handleBatchAction = useCallback(async (action: BatchAction) => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0 || batchLoading) return
    setBatchLoading(true)
    try {
      const result = await batchWorkflows(ids, action)
      if (result.failed > 0) {
        toast.error(`${result.success} 成功, ${result.failed} 失败`)
      } else {
        toast.success(`已处理 ${result.success} 项`)
      }
      setSelectedIds(new Set())
      await refresh()
      onRefresh()
    } catch (err: unknown) {
      toast.error(extractApiError(err) || '批量操作失败')
    } finally {
      setBatchLoading(false)
    }
  }, [selectedIds, batchLoading, refresh, onRefresh, toast])

  // 批量删除确认
  const handleBatchDelete = useCallback(() => {
    setConfirmState({
      open: true,
      message: `确认删除选中的 ${selectedIds.size} 个工作流及其所有执行历史?`,
      onConfirm: async () => {
        await handleBatchAction('delete')
        setConfirmState((s) => ({ ...s, open: false }))
      },
    })
  }, [selectedIds.size, handleBatchAction])

  // 打开版本历史
  const handleOpenVersionHistory = useCallback((id: string) => {
    setVersionHistoryId(id)
    setVersionHistoryOpen(true)
  }, [])

  const handleRenameKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>, id: string) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleRenameSubmit(id)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      handleRenameCancel()
    }
  }, [handleRenameSubmit, handleRenameCancel])

  const handleRenameBlur = useCallback((e: FocusEvent<HTMLInputElement>, id: string) => {
    // 焦点移向同编辑区域内其他控件（如标签输入框）时，不触发提交
    const related = e.relatedTarget as HTMLElement | null
    if (related && related.closest('[data-editing-area="true"]')) {
      return
    }
    const trimmed = editingName.trim()
    if (!trimmed) {
      handleRenameCancel()
    } else {
      handleRenameSubmit(id)
    }
  }, [editingName, handleRenameCancel, handleRenameSubmit])

  // 清空批量选择(供 BatchToolbar 取消按钮使用)
  const clearSelection = useCallback(() => setSelectedIds(new Set()), [])

  return (
    <TooltipProvider delayDuration={300}>
      <div className="workflow-list flex flex-col gap-3 p-3">
        {/* 顶部工具栏：标题 + 导入/刷新按钮 */}
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-base font-semibold text-foreground">已保存工作流</h3>
          <div className="flex items-center gap-1">
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={handleImportClick}
                  aria-label="导入工作流"
                >
                  <Download size={16} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>导入工作流</TooltipContent>
            </Tooltip>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={refresh}
                  disabled={loading}
                  aria-label="刷新工作流列表"
                >
                  {loading ? <Loader size={16} className="animate-spin" /> : <RefreshCw size={16} />}
                </Button>
              </TooltipTrigger>
              <TooltipContent>刷新</TooltipContent>
            </Tooltip>
          </div>
          <input
            type="file"
            accept=".json"
            ref={fileInputRef}
            style={{ display: 'none' }}
            onChange={handleFileChange}
          />
        </div>

        {/* 搜索框 + 筛选下拉 + 标签筛选 */}
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search
              size={14}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
            />
            <Input
              type="text"
              className="pl-8"
              placeholder="搜索工作流..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <Select
            value={filterTrigger}
            onValueChange={(v) => setFilterTrigger(v as FilterTrigger)}
          >
            <SelectTrigger className="w-[140px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部</SelectItem>
              <SelectItem value="manual">手动触发</SelectItem>
              <SelectItem value="schedule">定时触发</SelectItem>
              <SelectItem value="webhook">Webhook 触发</SelectItem>
            </SelectContent>
          </Select>
          {/* 标签筛选下拉（多选） */}
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="outline"
                size="sm"
                className="h-9 shrink-0"
                aria-label="标签筛选"
              >
                <Tag size={14} className="mr-1" />
                标签
                {tagFilter.size > 0 && (
                  <Badge variant="secondary" className="ml-1 px-1.5 py-0 text-[10px]">
                    {tagFilter.size}
                  </Badge>
                )}
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              {allTags.length === 0 ? (
                <DropdownMenuItem disabled>暂无标签</DropdownMenuItem>
              ) : (
                allTags.map((tag) => (
                  <DropdownMenuItem
                    key={tag}
                    onSelect={(e) => e.preventDefault()}
                    className="gap-2"
                  >
                    <input
                      type="checkbox"
                      checked={tagFilter.has(tag)}
                      onChange={() => toggleTagFilter(tag)}
                      className="h-3.5 w-3.5 cursor-pointer rounded border-border"
                      aria-label={`筛选标签 ${tag}`}
                    />
                    <span className="truncate text-sm">{tag}</span>
                  </DropdownMenuItem>
                ))
              )}
              {tagFilter.size > 0 && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onSelect={(e) => e.preventDefault()}
                    onClick={() => setTagFilter(new Set())}
                  >
                    <X size={14} className="mr-2" />
                    清除筛选
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* 批量操作工具栏(选中时显示,内部自带 selectedCount===0 返回 null 的守卫) */}
        <BatchToolbar
          selectedCount={selectedIds.size}
          batchLoading={batchLoading}
          onBatchAction={handleBatchAction}
          onBatchDelete={handleBatchDelete}
          onClearSelection={clearSelection}
        />

        {loading ? (
          // 加载态：渲染骨架卡片占位
          <div className="flex flex-col gap-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        ) : loadError ? (
          // 加载失败：展示错误信息 + 重试按钮
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <p className="text-sm text-destructive">{loadError}</p>
            <Button variant="outline" size="sm" onClick={refresh}>
              重试
            </Button>
          </div>
        ) : filteredWorkflows.length === 0 ? (
          workflows.length === 0 ? (
            // 列表为空：用 Card 包裹 EmptyState
            <Card className="border-dashed">
              <CardContent className="flex items-center justify-center py-10">
                <EmptyState
                  icon={<Inbox size={24} />}
                  title="暂无工作流"
                  description="输入需求开始创建"
                />
              </CardContent>
            </Card>
          ) : (
            // 筛选无匹配：保持轻量提示
            <p className="py-6 text-center text-sm text-muted-foreground">无匹配的工作流</p>
          )
        ) : (
          <div className="m-0 p-0 flex flex-col gap-3">
            <AnimatePresence mode="popLayout">
            {filteredWorkflows.map((wf) => {
              const isEditing = editingId === wf.id
              // 非编辑卡片传入常量值,避免每次渲染创建新引用破坏 React.memo
              return (
                <WorkflowCard
                  key={wf.id}
                  wf={wf}
                  isActive={currentWorkflowId === wf.id}
                  isSelected={selectedIds.has(wf.id)}
                  isEditing={isEditing}
                  isActionLoading={actionLoading === wf.id}
                  editingName={isEditing ? editingName : ''}
                  editingTags={isEditing ? editingTags : EMPTY_TAGS}
                  tagInput={isEditing ? tagInput : ''}
                  webhookUrl={
                    wf.webhook_id
                      ? `${API_BASE_URL}/api/webhooks/${wf.webhook_id}`
                      : null
                  }
                  onLoad={onLoad}
                  onToggleSelect={toggleSelect}
                  onStartRename={handleStartRename}
                  onRenameKeyDown={handleRenameKeyDown}
                  onRenameBlur={handleRenameBlur}
                  onEditingNameChange={setEditingName}
                  onRemoveEditingTag={removeEditingTag}
                  onTagInputChange={setTagInput}
                  onTagInputKeyDown={handleTagInputKeyDown}
                  onDuplicate={handleDuplicate}
                  onToggleSchedule={handleToggleSchedule}
                  onOpenVersionHistory={handleOpenVersionHistory}
                  onDelete={handleDelete}
                  onCopyWebhook={handleCopyWebhook}
                />
              )
            })}
            </AnimatePresence>
          </div>
        )}
        {/* 确认对话框（替代原生 confirm，用于删除工作流确认） */}
        <ConfirmDialog
          open={confirmState.open}
          title="确认操作"
          message={confirmState.message}
          danger
          confirmText="删除"
          onConfirm={confirmState.onConfirm}
          onCancel={() => setConfirmState((s) => ({ ...s, open: false }))}
        />
        {/* 版本历史侧滑面板 */}
        <VersionHistory
          workflowId={versionHistoryId}
          open={versionHistoryOpen}
          onOpenChange={setVersionHistoryOpen}
          onRestored={() => {
            refresh()
            onRefresh()
          }}
        />
      </div>
    </TooltipProvider>
  )
})
