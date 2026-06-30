import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

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

// Mock API:拦截凭证列表/保存/测试网络请求
vi.mock('../../services/api', () => ({
  getCredentials: vi.fn(),
  updateCredential: vi.fn(),
  testCredential: vi.fn(),
}))

import { CredentialPanel } from '../CredentialPanel'
import { getCredentials, updateCredential, testCredential } from '../../services/api'

const mockGetCredentials = vi.mocked(getCredentials)
const mockUpdateCredential = vi.mocked(updateCredential)
const mockTestCredential = vi.mocked(testCredential)

describe('CredentialPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('渲染凭证列表(分组展示 display_name 与配置状态)', async () => {
    mockGetCredentials.mockResolvedValue([
      {
        key: 'smtp_host',
        category: '邮件',
        display_name: 'SMTP 服务器',
        type: 'text',
        configured: true,
        value: 'smtp.example.com',
      },
      {
        key: 'smtp_pass',
        category: '邮件',
        display_name: 'SMTP 密码',
        type: 'secret',
        configured: false,
        value: '',
      },
    ])
    render(<CredentialPanel onClose={vi.fn()} />)
    expect(await screen.findByText('SMTP 服务器')).toBeInTheDocument()
    expect(screen.getByText('SMTP 密码')).toBeInTheDocument()
    expect(screen.getByText('已配置')).toBeInTheDocument()
    expect(screen.getByText('未配置')).toBeInTheDocument()
  })

  it('表单校验:空值时保存按钮禁用,输入后可保存', async () => {
    mockGetCredentials.mockResolvedValue([
      {
        key: 'k1',
        category: '邮件',
        display_name: 'API Key',
        type: 'text',
        configured: false,
        value: '',
      },
    ])
    mockUpdateCredential.mockResolvedValue(undefined)
    render(<CredentialPanel onClose={vi.fn()} />)
    const saveBtn = await screen.findByRole('button', { name: '保存' })
    // 空值时保存按钮禁用
    expect(saveBtn).toBeDisabled()
    // 输入值后启用
    const input = screen.getByPlaceholderText('请输入值')
    fireEvent.change(input, { target: { value: 'newval' } })
    expect(saveBtn).not.toBeDisabled()
    fireEvent.click(saveBtn)
    await waitFor(() => expect(mockUpdateCredential).toHaveBeenCalledWith('k1', 'newval'))
  })

  it('点击测试按钮调用 testCredential 并展示结果', async () => {
    mockGetCredentials.mockResolvedValue([
      {
        key: 'k1',
        category: '邮件',
        display_name: 'API Key',
        type: 'text',
        configured: true,
        value: 'v1',
      },
    ])
    mockTestCredential.mockResolvedValue({ success: true, message: '连通正常' })
    render(<CredentialPanel onClose={vi.fn()} />)
    const testBtn = await screen.findByRole('button', { name: '测试' })
    fireEvent.click(testBtn)
    await waitFor(() => expect(mockTestCredential).toHaveBeenCalledWith('k1'))
    expect(await screen.findByText('连通正常')).toBeInTheDocument()
  })

  it('加载失败显示错误信息', async () => {
    mockGetCredentials.mockRejectedValue(new Error('网络错误'))
    render(<CredentialPanel onClose={vi.fn()} />)
    await waitFor(() => expect(screen.getByText('网络错误')).toBeInTheDocument())
  })

  it('新凭证分组(LLM/Notion/飞书/通知)正确渲染分组标题与 display_name', async () => {
    mockGetCredentials.mockResolvedValue([
      { key: 'LLM_API_KEY', category: 'LLM', display_name: 'LLM API Key', type: 'secret', configured: true, value: '****3456' },
      { key: 'LLM_MODEL', category: 'LLM', display_name: '默认模型', type: 'text', configured: true, value: 'agnes-2.0-flash' },
      { key: 'NOTION_TOKEN', category: 'Notion', display_name: 'Notion 集成 Token', type: 'secret', configured: false, value: '' },
      { key: 'FEISHU_WEBHOOK_URL', category: '飞书', display_name: '飞书机器人 Webhook URL', type: 'text', configured: false, value: '' },
      { key: 'FAILURE_NOTIFY_EMAIL', category: '通知', display_name: '失败通知收件邮箱', type: 'text', configured: false, value: '' },
    ])
    render(<CredentialPanel onClose={vi.fn()} />)
    // 各分组标题出现(span 文本精确匹配)
    expect(await screen.findByText('LLM')).toBeInTheDocument()
    expect(screen.getByText('Notion')).toBeInTheDocument()
    expect(screen.getByText('飞书')).toBeInTheDocument()
    expect(screen.getByText('通知')).toBeInTheDocument()
    // display_name 出现
    expect(screen.getByText('LLM API Key')).toBeInTheDocument()
    expect(screen.getByText('默认模型')).toBeInTheDocument()
    expect(screen.getByText('Notion 集成 Token')).toBeInTheDocument()
    expect(screen.getByText('飞书机器人 Webhook URL')).toBeInTheDocument()
    expect(screen.getByText('失败通知收件邮箱')).toBeInTheDocument()
  })
})
