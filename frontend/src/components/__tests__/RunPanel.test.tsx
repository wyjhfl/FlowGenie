import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import type { ParseResponse, RunResult } from '../../types/workflow'

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

// Mock API:调试模式相关接口在非调试用例中不会被调用,仍 mock 以隔离网络
vi.mock('../../services/api', () => ({
  runWorkflowStream: vi.fn(() => new AbortController()),
  stepNext: vi.fn(),
  stepContinue: vi.fn(),
  stepAbort: vi.fn(),
}))

import { RunPanel } from '../RunPanel'

const workflow: ParseResponse = {
  scenario: '测试场景',
  summary: '测试摘要',
  steps: [
    { id: 's1', name: '步骤一', description: '', tool: 't1', params: {} },
    { id: 's2', name: '步骤二', description: '', tool: 't2', params: {} },
    { id: 's3', name: '步骤三', description: '', tool: 't3', params: {} },
  ],
  edges: [],
  source: 'llm',
}

describe('RunPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('空态:无工作流时显示提示', () => {
    render(
      <RunPanel workflow={null} runResult={null} onRun={vi.fn()} running={false} />
    )
    expect(screen.getByText('请先生成工作流')).toBeInTheDocument()
  })

  it('渲染步骤状态(成功/失败/运行中)', () => {
    const runResult: RunResult = {
      status: 'partial_success',
      steps_result: {
        s1: { output: 'ok', status: 'success', error: null, time_ms: 100 },
        s2: { output: null, status: 'failed', error: '超时', time_ms: 200 },
        s3: { output: null, status: 'running' },
      },
      total_time_ms: 300,
    }
    render(
      <RunPanel workflow={workflow} runResult={runResult} onRun={vi.fn()} running={false} />
    )
    // 总状态(部分成功)与各步骤状态徽标
    expect(screen.getByText('部分成功')).toBeInTheDocument()
    expect(screen.getByText('成功')).toBeInTheDocument()
    expect(screen.getByText('失败')).toBeInTheDocument()
    expect(screen.getByText('执行中')).toBeInTheDocument()
  })

  it('日志渲染:展示实时日志条目', () => {
    const logs = [
      {
        time: '2026-06-26T10:00:00Z',
        step_id: 's1',
        event: 'success' as const,
        message: '',
        time_ms: 100,
      },
    ]
    render(
      <RunPanel workflow={workflow} runResult={null} onRun={vi.fn()} running={false} logs={logs} />
    )
    expect(screen.getByText('实时日志')).toBeInTheDocument()
    expect(screen.getByText('s1')).toBeInTheDocument()
    expect(screen.getByText(/完成/)).toBeInTheDocument()
  })

  it('点击执行按钮触发 onRun 回调', () => {
    const onRun = vi.fn()
    render(
      <RunPanel workflow={workflow} runResult={null} onRun={onRun} running={false} />
    )
    const btn = screen.getByRole('button', { name: /执行工作流/ })
    fireEvent.click(btn)
    expect(onRun).toHaveBeenCalledTimes(1)
  })

  it('B2: running 步骤有 streamingTokens 时显示流式 token 文本与光标', () => {
    const runResult: RunResult = {
      status: 'running',
      steps_result: {
        s1: { output: null, status: 'running' },
      },
      total_time_ms: 0,
    }
    const streamingTokens = { s1: '正在生成' }
    render(
      <RunPanel
        workflow={workflow}
        runResult={runResult}
        onRun={vi.fn()}
        running={true}
        streamingTokens={streamingTokens}
      />
    )
    expect(screen.getByText('流式输出中')).toBeInTheDocument()
    expect(screen.getByText('正在生成')).toBeInTheDocument()
  })

  it('B2: 步骤完成(status=success)时不显示流式 token,改显完整输出', () => {
    const runResult: RunResult = {
      status: 'success',
      steps_result: {
        s1: { output: '完整结果', status: 'success', error: null, time_ms: 50 },
      },
      total_time_ms: 50,
    }
    // 即使 streamingTokens 仍有残留(理论上 onStep 会清除),success 状态也不显示流式区
    const streamingTokens = { s1: '残留token' }
    render(
      <RunPanel
        workflow={workflow}
        runResult={runResult}
        onRun={vi.fn()}
        running={false}
        streamingTokens={streamingTokens}
      />
    )
    // success 状态不显示"流式输出中"
    expect(screen.queryByText('流式输出中')).not.toBeInTheDocument()
    expect(screen.queryByText('残留token')).not.toBeInTheDocument()
  })

  it('B2: 无 streamingTokens 时 running 步骤不显示流式区', () => {
    const runResult: RunResult = {
      status: 'running',
      steps_result: {
        s1: { output: null, status: 'running' },
      },
      total_time_ms: 0,
    }
    render(
      <RunPanel workflow={workflow} runResult={runResult} onRun={vi.fn()} running={true} />
    )
    expect(screen.queryByText('流式输出中')).not.toBeInTheDocument()
  })
})
