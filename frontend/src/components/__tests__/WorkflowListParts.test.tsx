// WorkflowListParts 子组件测试(WorkflowCard / BatchToolbar)
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TooltipProvider } from '@/components/ui/Tooltip'

// Mock framer-motion:jsdom 下动画无意义,透传 div 避免渲染问题
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => {
      const { initial, animate, transition, exit, whileHover, layout, ...rest } = props
      void initial
      void animate
      void transition
      void exit
      void whileHover
      void layout
      return <div {...rest}>{children}</div>
    },
  },
}))

import { WorkflowCard, BatchToolbar, type WorkflowCardItem } from '../WorkflowListParts'

// 构造一个无操作回调集合,避免每个用例重复
const noopHandlers = () => ({
  onLoad: vi.fn(),
  onToggleSelect: vi.fn(),
  onStartRename: vi.fn(),
  onRenameKeyDown: vi.fn(),
  onRenameBlur: vi.fn(),
  onEditingNameChange: vi.fn(),
  onRemoveEditingTag: vi.fn(),
  onTagInputChange: vi.fn(),
  onTagInputKeyDown: vi.fn(),
  onDuplicate: vi.fn(),
  onToggleSchedule: vi.fn(),
  onOpenVersionHistory: vi.fn(),
  onDelete: vi.fn(),
  onCopyWebhook: vi.fn(),
})

const baseWf: WorkflowCardItem = {
  id: 'wf-1',
  name: 'Alpha',
  scenario: '场景一',
  schedule_enabled: false,
  webhook_id: null,
  triggers: [],
  tags: ['prod'],
  created_at: '2026-06-26T10:00:00Z',
  updated_at: '2026-06-26T10:00:00Z',
}

describe('WorkflowCard', () => {
  it('渲染名称/场景/标签(非编辑态)', () => {
    const h = noopHandlers()
    render(
      <WorkflowCard
        wf={baseWf}
        isActive={false}
        isSelected={false}
        isEditing={false}
        isActionLoading={false}
        editingName=""
        editingTags={[]}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('场景一')).toBeInTheDocument()
    expect(screen.getByText('prod')).toBeInTheDocument()
  })

  it('schedule_enabled 与 webhook_id 同时存在时显示两个 Badge', () => {
    const h = noopHandlers()
    render(
      <TooltipProvider>
        <WorkflowCard
          wf={{ ...baseWf, schedule_enabled: true, webhook_id: 'wh-1' }}
          isActive={false}
          isSelected={false}
          isEditing={false}
          isActionLoading={false}
          editingName=""
          editingTags={[]}
          tagInput=""
          webhookUrl="http://localhost/api/webhooks/wh-1"
          {...h}
        />
      </TooltipProvider>
    )
    expect(screen.getByText('调度')).toBeInTheDocument()
    expect(screen.getByText('Webhook')).toBeInTheDocument()
  })

  it('点击卡片触发 onLoad', () => {
    const h = noopHandlers()
    const { container } = render(
      <WorkflowCard
        wf={baseWf}
        isActive={false}
        isSelected={false}
        isEditing={false}
        isActionLoading={false}
        editingName=""
        editingTags={[]}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    // 卡片外层 div 带 role="button"(原生 dropdown trigger 也匹配 getByRole,故用 querySelector 精确定位)
    const cardEl = container.querySelector('[role="button"]')
    fireEvent.click(cardEl!)
    expect(h.onLoad).toHaveBeenCalledWith('wf-1')
  })

  it('点击 checkbox 触发 onToggleSelect(而非 onLoad)', () => {
    const h = noopHandlers()
    render(
      <WorkflowCard
        wf={baseWf}
        isActive={false}
        isSelected={false}
        isEditing={false}
        isActionLoading={false}
        editingName=""
        editingTags={[]}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    fireEvent.click(screen.getByLabelText('选择工作流 Alpha'))
    expect(h.onToggleSelect).toHaveBeenCalledWith('wf-1')
    // checkbox stopPropagation,不应触发卡片 onLoad
    expect(h.onLoad).not.toHaveBeenCalled()
  })

  it('编辑态显示输入框(值为 editingName)而非静态标题', () => {
    const h = noopHandlers()
    render(
      <WorkflowCard
        wf={baseWf}
        isActive={false}
        isSelected={false}
        isEditing={true}
        isActionLoading={false}
        editingName="新名称"
        editingTags={['a']}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    const input = screen.getByDisplayValue('新名称') as HTMLInputElement
    expect(input).toBeInTheDocument()
    // 编辑态不显示静态标题(双击重命名)
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument()
    // 编辑态显示已编辑标签
    expect(screen.getByText('a')).toBeInTheDocument()
  })

  it('双击标题触发 onStartRename', () => {
    const h = noopHandlers()
    render(
      <WorkflowCard
        wf={baseWf}
        isActive={false}
        isSelected={false}
        isEditing={false}
        isActionLoading={false}
        editingName=""
        editingTags={[]}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    fireEvent.doubleClick(screen.getByText('Alpha'))
    expect(h.onStartRename).toHaveBeenCalledWith(baseWf)
  })

  it('isActive 高亮:渲染 ring 标识(通过 class 含 ring-primary)', () => {
    const h = noopHandlers()
    const { container } = render(
      <WorkflowCard
        wf={baseWf}
        isActive={true}
        isSelected={false}
        isEditing={false}
        isActionLoading={false}
        editingName=""
        editingTags={[]}
        tagInput=""
        webhookUrl={null}
        {...h}
      />
    )
    // 卡片外层 div(由 motion.div mock 透传),其内层 Card 含 ring-primary class
    const cardEl = container.querySelector('[role="button"]')
    expect(cardEl?.className).toContain('ring-primary')
  })
})

describe('BatchToolbar', () => {
  it('selectedCount=0 时返回 null(不渲染)', () => {
    const { container } = render(
      <BatchToolbar
        selectedCount={0}
        batchLoading={false}
        onBatchAction={vi.fn()}
        onBatchDelete={vi.fn()}
        onClearSelection={vi.fn()}
      />
    )
    expect(container.firstChild).toBeNull()
  })

  it('selectedCount>0 时显示计数与三个操作按钮', () => {
    render(
      <BatchToolbar
        selectedCount={3}
        batchLoading={false}
        onBatchAction={vi.fn()}
        onBatchDelete={vi.fn()}
        onClearSelection={vi.fn()}
      />
    )
    expect(screen.getByText('已选 3 项')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '启用调度' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '禁用调度' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '批量删除' })).toBeInTheDocument()
  })

  it('点击启用调度触发 onBatchAction("enable_schedule")', () => {
    const onBatchAction = vi.fn()
    render(
      <BatchToolbar
        selectedCount={2}
        batchLoading={false}
        onBatchAction={onBatchAction}
        onBatchDelete={vi.fn()}
        onClearSelection={vi.fn()}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: '启用调度' }))
    expect(onBatchAction).toHaveBeenCalledWith('enable_schedule')
  })

  it('batchLoading=true 时所有按钮禁用', () => {
    render(
      <BatchToolbar
        selectedCount={1}
        batchLoading={true}
        onBatchAction={vi.fn()}
        onBatchDelete={vi.fn()}
        onClearSelection={vi.fn()}
      />
    )
    expect(screen.getByRole('button', { name: '启用调度' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '批量删除' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '取消选择' })).toBeDisabled()
  })
})
