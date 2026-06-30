import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import type { WorkflowVersion } from '../../types/workflow'

// 使用 vi.hoisted 确保 mockToast 在 vi.mock 工厂执行前已就绪
const { mockToast } = vi.hoisted(() => ({
  mockToast: {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    show: vi.fn(),
  },
}))

// Mock toast:避免 ToastProvider 依赖,并允许断言 error 调用
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => mockToast,
}))

// Mock API:拦截版本列表/回滚网络请求
vi.mock('../../services/api', () => ({
  listVersions: vi.fn(),
  restoreVersion: vi.fn(),
}))

import { VersionHistory } from '../VersionHistory'
import { listVersions, restoreVersion } from '../../services/api'

const mockListVersions = vi.mocked(listVersions)
const mockRestoreVersion = vi.mocked(restoreVersion)

const versions: WorkflowVersion[] = [
  {
    id: 'vid-2',
    workflow_id: 'wf-1',
    version_number: 2,
    steps: [
      { id: 's1', name: 'n1', description: '', tool: 'llm_summary', params: {} },
    ],
    edges: [],
    summary: '',
    on_failure: 'stop',
    tags: [],
    note: '修复问题',
    created_at: '2026-06-26T10:00:00Z',
  },
  {
    id: 'vid-1',
    workflow_id: 'wf-1',
    version_number: 1,
    steps: [],
    edges: [],
    summary: '',
    on_failure: 'stop',
    tags: [],
    note: '',
    created_at: '2026-06-25T10:00:00Z',
  },
]

describe('VersionHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('版本列表渲染', async () => {
    mockListVersions.mockResolvedValue(versions)
    render(
      <VersionHistory
        workflowId="wf-1"
        open={true}
        onOpenChange={vi.fn()}
        onRestored={vi.fn()}
      />
    )
    expect(await screen.findByText('v2')).toBeInTheDocument()
    expect(screen.getByText('v1')).toBeInTheDocument()
  })

  it('回滚操作:确认后调用 restoreVersion 与 onRestored', async () => {
    mockListVersions.mockResolvedValue(versions)
    mockRestoreVersion.mockResolvedValue({} as never)
    const onRestored = vi.fn()
    render(
      <VersionHistory
        workflowId="wf-1"
        open={true}
        onOpenChange={vi.fn()}
        onRestored={onRestored}
      />
    )
    await screen.findByText('v2')
    // 点击第一行的"回滚"按钮(列表中存在多个回滚按钮)
    const rollbackBtns = screen.getAllByText('回滚')
    fireEvent.click(rollbackBtns[0])
    // 确认对话框打开,在对话框作用域内点击"回滚"确认按钮
    const dialog = await screen.findByRole('alertdialog')
    const confirmBtn = within(dialog).getByRole('button', { name: '回滚' })
    fireEvent.click(confirmBtn)
    await waitFor(() => expect(mockRestoreVersion).toHaveBeenCalledWith('wf-1', 'vid-2'))
    await waitFor(() => expect(onRestored).toHaveBeenCalled())
  })

  it('空态:无版本时显示提示', async () => {
    mockListVersions.mockResolvedValue([])
    render(
      <VersionHistory
        workflowId="wf-1"
        open={true}
        onOpenChange={vi.fn()}
        onRestored={vi.fn()}
      />
    )
    expect(await screen.findByText('暂无版本历史')).toBeInTheDocument()
  })

  it('加载失败调用 toast.error', async () => {
    mockListVersions.mockRejectedValue(new Error('网络错误'))
    render(
      <VersionHistory
        workflowId="wf-1"
        open={true}
        onOpenChange={vi.fn()}
        onRestored={vi.fn()}
      />
    )
    await waitFor(() => expect(mockToast.error).toHaveBeenCalledWith('网络错误'))
  })
})
