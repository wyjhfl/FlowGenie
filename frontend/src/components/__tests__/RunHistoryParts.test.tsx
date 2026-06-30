// RunHistoryParts 子组件测试(StepCards / RunLogs / RunDiffPanel)
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StepCards, RunLogs, RunDiffPanel } from '../RunHistoryParts'
import type { RunDiff } from '../../services/api'

describe('StepCards', () => {
  it('无步骤结果时显示空态提示', () => {
    render(
      <StepCards
        stepsResult={{}}
        stepMap={{}}
        runId="r1"
        expandedOutputs={new Set()}
        expandedErrors={new Set()}
        onToggleOutput={vi.fn()}
        onToggleError={vi.fn()}
      />
    )
    expect(screen.getByText('无步骤结果')).toBeInTheDocument()
  })

  it('按 step_id 渲染步骤名称与状态(自然排序 step_2 在 step_10 前)', () => {
    const stepsResult = {
      step_10: { status: 'success', output: 'ten' },
      step_2: { status: 'failed', error: 'boom' },
    }
    render(
      <StepCards
        stepsResult={stepsResult}
        stepMap={{
          step_2: { id: 'step_2', name: '第二步', description: '', tool: 't', params: {} },
          step_10: { id: 'step_10', name: '第十步', description: '', tool: 't', params: {} },
        }}
        runId="r1"
        expandedOutputs={new Set()}
        expandedErrors={new Set()}
        onToggleOutput={vi.fn()}
        onToggleError={vi.fn()}
      />
    )
    const names = screen.getAllByText(/第[二十]步/).map((el) => el.textContent)
    expect(names[0]).toBe('第二步')
    expect(names[1]).toBe('第十步')
  })

  it('点击"展开全部"按钮调用 onToggleOutput(超长输出场景)', () => {
    const longOutput = 'x'.repeat(300)
    const onToggleOutput = vi.fn()
    render(
      <StepCards
        stepsResult={{ s1: { status: 'success', output: longOutput } }}
        stepMap={{ s1: { id: 's1', name: '步骤一', description: '', tool: 't', params: {} } }}
        runId="r1"
        expandedOutputs={new Set()}
        expandedErrors={new Set()}
        onToggleOutput={onToggleOutput}
        onToggleError={vi.fn()}
      />
    )
    const btn = screen.getByText('展开全部')
    fireEvent.click(btn)
    expect(onToggleOutput).toHaveBeenCalledWith('r1-s1-output')
  })
})

describe('RunLogs', () => {
  it('无日志时返回 null(不渲染切换按钮)', () => {
    const { container } = render(
      <RunLogs runId="r1" logs={[]} isExpanded={false} onToggle={vi.fn()} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('点击日志切换按钮调用 onToggle,展开后显示日志消息', () => {
    const onToggle = vi.fn()
    const { rerender } = render(
      <RunLogs
        runId="r1"
        logs={[{ timestamp: 1700000000, level: 'INFO', module: 'exec', message: '开始执行' }]}
        isExpanded={false}
        onToggle={onToggle}
      />
    )
    // 收起时不显示日志内容
    expect(screen.queryByText('开始执行')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button'))
    expect(onToggle).toHaveBeenCalledWith('r1')

    // 展开后渲染日志内容
    rerender(
      <RunLogs
        runId="r1"
        logs={[{ timestamp: 1700000000, level: 'INFO', module: 'exec', message: '开始执行' }]}
        isExpanded={true}
        onToggle={onToggle}
      />
    )
    expect(screen.getByText('开始执行')).toBeInTheDocument()
  })
})

describe('RunDiffPanel', () => {
  const baseProps = {
    diffResult: null as RunDiff | null,
    diffLoading: false,
    diffError: null as string | null,
    onClose: vi.fn(),
  }

  it('全部为空时不渲染面板', () => {
    const { container } = render(<RunDiffPanel {...baseProps} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('loading 时显示加载提示', () => {
    render(<RunDiffPanel {...baseProps} diffLoading={true} />)
    expect(screen.getByText('加载对比数据...')).toBeInTheDocument()
  })

  it('error 时显示错误信息', () => {
    render(<RunDiffPanel {...baseProps} diffError="对比失败" />)
    expect(screen.getByText('对比失败')).toBeInTheDocument()
  })

  it('有结果时渲染步骤对比表格与变化行高亮', () => {
    const diff: RunDiff = {
      run1: { id: 'aaaaaaaa', status: 'success', total_time_ms: 100, started_at: '2024-01-01T00:00:00', trigger_type: 'manual' },
      run2: { id: 'bbbbbbbb', status: 'failed', total_time_ms: 200, started_at: '2024-01-02T00:00:00', trigger_type: 'manual' },
      steps: [
        { step_id: 's1', name: '步骤一', status1: 'success', status2: 'failed', time1: 50, time2: 60, error1: null, error2: '超时', changed: true },
        { step_id: 's2', name: '步骤二', status1: 'success', status2: 'success', time1: 30, time2: 30, error1: null, error2: null, changed: false },
      ],
    }
    render(<RunDiffPanel {...baseProps} diffResult={diff} />)
    // 步骤名同时出现在表格与"错误变化详情"区,故用 getAllByText
    expect(screen.getAllByText('步骤一').length).toBeGreaterThan(0)
    expect(screen.getAllByText('步骤二').length).toBeGreaterThan(0)
    // 错误变化详情区显示变化步骤的错误
    expect(screen.getByText('超时')).toBeInTheDocument()
    // 点击关闭按钮调用 onClose(面板内唯一的按钮)
    fireEvent.click(screen.getByRole('button'))
    expect(baseProps.onClose).toHaveBeenCalled()
  })
})
