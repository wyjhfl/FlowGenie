import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock framer-motion:jsdom 下动画无意义,用透传 div 替代避免渲染问题
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => {
      const { initial, animate, transition, ...rest } = props
      void initial
      void animate
      void transition
      return <div {...(rest as Record<string, unknown>)}>{children as React.ReactNode}</div>
    },
  },
}))

// Mock getDashboardStats:拦截网络请求,返回可控数据
vi.mock('../../services/api', () => ({
  getDashboardStats: vi.fn(),
}))

import { DashboardPanel } from '../DashboardPanel'
import { getDashboardStats } from '../../services/api'

const mockGetDashboardStats = vi.mocked(getDashboardStats)

const mockStats = {
  total_runs: 10,
  success_count: 8,
  failed_count: 2,
  partial_success_count: 0,
  success_rate: 80,
  avg_time_ms: 1500,
  trend: [{ date: '2026-06-26', total: 5, success: 4, failed: 1 }],
  tool_usage: [{ tool: 'llm_summary', count: 3 }],
  workflow_ranking: [],
  failure_clusters: [],
  duration_percentiles: { p50: 1000, p90: 2000, p95: 2500, max: 3000 },
  token_stats: {
    total_tokens: 0,
    prompt_tokens: 0,
    completion_tokens: 0,
    calls: 0,
    by_model: {},
  },
}

describe('DashboardPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('加载中禁用刷新按钮', () => {
    // 返回永不 resolve 的 Promise,保持 loading 状态
    mockGetDashboardStats.mockReturnValue(new Promise(() => {}))
    render(<DashboardPanel onClose={vi.fn()} />)
    const refreshBtn = screen.getByLabelText('刷新统计数据')
    expect(refreshBtn).toBeDisabled()
  })

  it('加载失败显示错误信息', async () => {
    mockGetDashboardStats.mockRejectedValue(new Error('网络错误'))
    render(<DashboardPanel onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('网络错误')).toBeInTheDocument()
    })
  })

  it('无执行数据显示空状态', async () => {
    mockGetDashboardStats.mockResolvedValue({ ...mockStats, total_runs: 0 })
    render(<DashboardPanel onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('暂无执行数据')).toBeInTheDocument()
    })
  })

  it('正确渲染统计卡片数值', async () => {
    mockGetDashboardStats.mockResolvedValue(mockStats)
    render(<DashboardPanel onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('总执行数')).toBeInTheDocument()
      expect(screen.getByText('80%')).toBeInTheDocument()
      expect(screen.getByText('1.5s')).toBeInTheDocument()
    })
  })

  it('切换天数触发新请求', async () => {
    mockGetDashboardStats.mockResolvedValue(mockStats)
    render(<DashboardPanel onClose={vi.fn()} />)
    const user = userEvent.setup()
    // 等待初始加载完成(days 切换按钮仅在数据加载后渲染)
    const btn30 = await screen.findByText('30天')
    await user.click(btn30)
    await waitFor(() => {
      expect(mockGetDashboardStats).toHaveBeenCalledWith(30)
    })
  })

  it('B4: 无 token 用量时不渲染 Token 卡片', async () => {
    // mockStats.token_stats.total_tokens = 0,不应显示 Token 卡片
    mockGetDashboardStats.mockResolvedValue(mockStats)
    render(<DashboardPanel onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('总执行数')).toBeInTheDocument()
    })
    expect(screen.queryByText('LLM Token 用量')).not.toBeInTheDocument()
  })

  it('B4: 有 token 用量时渲染 Token 卡片与按模型分布', async () => {
    mockGetDashboardStats.mockResolvedValue({
      ...mockStats,
      token_stats: {
        total_tokens: 1500,
        prompt_tokens: 1000,
        completion_tokens: 500,
        calls: 7,
        by_model: {
          'gpt-4o': { total_tokens: 1000, prompt_tokens: 700, completion_tokens: 300, calls: 5 },
          'agnes-flash': { total_tokens: 500, prompt_tokens: 300, completion_tokens: 200, calls: 2 },
        },
      },
    })
    render(<DashboardPanel onClose={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByText('LLM Token 用量')).toBeInTheDocument()
    })
    // 总量 1500 → "1.5k"(唯一,不与其他数字冲突)
    expect(screen.getByText('1.5k')).toBeInTheDocument()
    // 调用次数 7(与 mockStats 中其他数字不冲突)
    expect(screen.getByText('7')).toBeInTheDocument()
    // 按模型分布显示模型名
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
    expect(screen.getByText('agnes-flash')).toBeInTheDocument()
  })
})
