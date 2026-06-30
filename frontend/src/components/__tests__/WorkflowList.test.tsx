import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

// Mock framer-motion:jsdom 下动画无意义,透传 div/Fragment 避免渲染问题
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
  AnimatePresence: ({ children }: any) => <>{children}</>,
}))

// Mock toast:避免 ToastProvider 依赖
// 使用 vi.hoisted 确保返回稳定对象(真实 useToast 在 Provider 未重渲染时返回同一 context value)
const { toastMock } = vi.hoisted(() => ({
  toastMock: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    show: vi.fn(),
  },
}))
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => toastMock,
}))

// Mock VersionHistory 子组件:避免引入 Sheet/portal 复杂度,聚焦列表逻辑
vi.mock('../VersionHistory', () => ({
  VersionHistory: () => null,
}))

// Mock API:拦截工作流列表/批量操作等网络请求
vi.mock('../../services/api', () => ({
  listWorkflowsByTags: vi.fn(),
  deleteWorkflow: vi.fn(),
  enableSchedule: vi.fn(),
  disableSchedule: vi.fn(),
  importWorkflow: vi.fn(),
  duplicateWorkflow: vi.fn(),
  updateWorkflowWithTags: vi.fn(),
  batchWorkflows: vi.fn(),
}))

import { WorkflowList } from '../WorkflowList'
import { listWorkflowsByTags, batchWorkflows } from '../../services/api'

const mockListWorkflowsByTags = vi.mocked(listWorkflowsByTags)
const mockBatchWorkflows = vi.mocked(batchWorkflows)

const wf1 = {
  id: 'wf-1',
  name: 'Alpha',
  scenario: '场景一',
  schedule_enabled: false,
  webhook_id: null,
  triggers: [],
  tags: [],
  created_at: '2026-06-26T10:00:00Z',
  updated_at: '2026-06-26T10:00:00Z',
}
const wf2 = {
  id: 'wf-2',
  name: 'Beta',
  scenario: '场景二',
  schedule_enabled: true,
  webhook_id: 'wh-1',
  triggers: [],
  tags: [],
  created_at: '2026-06-26T10:00:00Z',
  updated_at: '2026-06-26T10:00:00Z',
}

describe('WorkflowList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染工作流列表(传入 mock 数据)', async () => {
    mockListWorkflowsByTags.mockResolvedValue([wf1, wf2])
    render(
      <WorkflowList currentWorkflowId={null} onLoad={vi.fn()} onRefresh={vi.fn()} />
    )
    expect(await screen.findByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('搜索过滤:输入关键词后列表变化', async () => {
    mockListWorkflowsByTags.mockResolvedValue([wf1, wf2])
    render(
      <WorkflowList currentWorkflowId={null} onLoad={vi.fn()} onRefresh={vi.fn()} />
    )
    await screen.findByText('Alpha')
    const search = screen.getByPlaceholderText('搜索工作流...')
    fireEvent.change(search, { target: { value: 'alp' } })
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.queryByText('Beta')).not.toBeInTheDocument()
  })

  it('空态:无工作流时显示提示', async () => {
    mockListWorkflowsByTags.mockResolvedValue([])
    render(
      <WorkflowList currentWorkflowId={null} onLoad={vi.fn()} onRefresh={vi.fn()} />
    )
    expect(await screen.findByText('暂无工作流')).toBeInTheDocument()
  })

  it('批量操作:选中多个后执行批量启用调度', async () => {
    mockListWorkflowsByTags.mockResolvedValue([wf1, wf2])
    mockBatchWorkflows.mockResolvedValue({ success: 2, failed: 0, failed_ids: [] })
    render(
      <WorkflowList currentWorkflowId={null} onLoad={vi.fn()} onRefresh={vi.fn()} />
    )
    await screen.findByText('Alpha')
    fireEvent.click(screen.getByLabelText('选择工作流 Alpha'))
    fireEvent.click(screen.getByLabelText('选择工作流 Beta'))
    expect(screen.getByText('已选 2 项')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '启用调度' }))
    await waitFor(() =>
      expect(mockBatchWorkflows).toHaveBeenCalledWith(
        ['wf-1', 'wf-2'],
        'enable_schedule'
      )
    )
  })
})
