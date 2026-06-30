import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import type { PreferenceItem } from '../../services/api'

// Mock toast:避免 ToastProvider 依赖
vi.mock('@/components/ui/Toast', () => ({
  useToast: () => ({
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    show: vi.fn(),
  }),
}))

// Mock API:拦截偏好 schema/读取/更新/删除网络请求
vi.mock('../../services/api', () => ({
  getPreferences: vi.fn(),
  getPreferenceSchema: vi.fn(),
  updatePreferences: vi.fn(),
  deletePreference: vi.fn(),
}))

import { PreferencePanel } from '../PreferencePanel'
import {
  getPreferences,
  getPreferenceSchema,
  updatePreferences,
  deletePreference,
} from '../../services/api'

const mockGetPreferences = vi.mocked(getPreferences)
const mockGetPreferenceSchema = vi.mocked(getPreferenceSchema)
const mockUpdatePreferences = vi.mocked(updatePreferences)
const mockDeletePreference = vi.mocked(deletePreference)

const schema: PreferenceItem[] = [
  {
    key: 'email_sender',
    category: '邮件',
    display_name: '发件邮箱',
    type: 'text',
    default: '',
    options: null,
    applicable_tools: {},
    description: '发件人邮箱地址',
  },
  {
    key: 'email_mode',
    category: '邮件',
    display_name: '发送模式',
    type: 'select',
    default: 'smtp',
    options: ['smtp', 'api'],
    applicable_tools: {},
    description: '发送方式',
  },
]

describe('PreferencePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetPreferenceSchema.mockResolvedValue(schema)
    mockGetPreferences.mockResolvedValue({ email_sender: 'a@b.com', email_mode: 'smtp' })
  })

  it('schema 驱动渲染:根据 schema 渲染表单字段', async () => {
    render(<PreferencePanel onClose={vi.fn()} />)
    expect(await screen.findByText('发件邮箱')).toBeInTheDocument()
    expect(screen.getByText('发送模式')).toBeInTheDocument()
    expect(screen.getByText('发件人邮箱地址')).toBeInTheDocument()
  })

  it('保存:点击保存触发 updatePreferences 调用', async () => {
    mockUpdatePreferences.mockResolvedValue(undefined)
    render(<PreferencePanel onClose={vi.fn()} />)
    await screen.findByText('发件邮箱')
    // schema 第一项(email_sender)的保存按钮
    const saveBtns = screen.getAllByRole('button', { name: '保存' })
    fireEvent.click(saveBtns[0])
    await waitFor(() =>
      expect(mockUpdatePreferences).toHaveBeenCalledWith({ email_sender: 'a@b.com' })
    )
  })

  it('删除:点击清除触发 deletePreference 调用', async () => {
    mockDeletePreference.mockResolvedValue(undefined)
    render(<PreferencePanel onClose={vi.fn()} />)
    await screen.findByText('发件邮箱')
    const delBtns = screen.getAllByLabelText('清除偏好')
    fireEvent.click(delBtns[0])
    await waitFor(() => expect(mockDeletePreference).toHaveBeenCalledWith('email_sender'))
  })

  it('加载失败显示错误信息', async () => {
    mockGetPreferenceSchema.mockRejectedValue(new Error('加载失败'))
    render(<PreferencePanel onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('加载失败')).toBeInTheDocument())
  })
})
