// SSE 流式执行封装(从 api.ts 抽出,保持单一职责)
// API_BASE_URL 本地重新派生,避免与 api.ts 形成循环依赖
import type { ParseResponse } from '../types/workflow'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://flowgenie-w8xb.onrender.com'

/** 流式执行工作流（SSE）
 *  返回 AbortController 供调用方中止流；超时与外部中止均通过 controller.abort() 触发。
 *  options.debug=true 启用调试模式（每步暂停）；options.onStart 收到 start 事件时回调（含 run_id）。
 *  options.onStepToken: B2 LLM 流式输出——收到 step_token 事件时回调(stepId, delta),前端实时累积显示。
 */
export function runWorkflowStream(
  workflow: ParseResponse,
  onStep: (data: { step_id: string; status: string; output: unknown; time_ms?: number; error?: string | null }) => void,
  onDone: (data: { status: string; total_time_ms: number; steps_result: Record<string, unknown> }) => void,
  onError: (error: string) => void,
  options?: {
    workflow_id?: string
    on_failure?: string
    debug?: boolean
    onStart?: (data: { run_id?: string; workflow_id?: string }) => void
    onStepToken?: (stepId: string, delta: string) => void
  }
): AbortController {
  const controller = new AbortController()
  // 5 分钟超时，长耗时工作流；超时后中止流
  const timeoutId = setTimeout(() => controller.abort(), 300000)

  const body: Record<string, unknown> = {
    steps: workflow.steps,
    edges: workflow.edges,
    trigger_data: null,
  }
  if (options?.workflow_id) body.workflow_id = options.workflow_id
  if (options?.on_failure) body.on_failure = options.on_failure

  const url = `${API_BASE_URL}/api/workflows/run/stream${options?.debug ? '?debug=true' : ''}`

  ;(async () => {
    let response: Response
    try {
      response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify(body),
        signal: controller.signal,
      })
    } catch (err) {
      clearTimeout(timeoutId)
      // 主动中止时不触发 onError
      if (!controller.signal.aborted) {
        onError(err instanceof Error ? err.message : '请求流式执行失败')
      }
      return
    }

    if (!response.ok || !response.body) {
      clearTimeout(timeoutId)
      onError(`流式执行请求失败: HTTP ${response.status}`)
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder('utf-8')
    let buffer = ''
    // 标记是否已收到终止事件（done/error），用于检测流异常中断
    let terminated = false

    // SSE 事件以空行分隔，兼容 \n\n / \r\n\r\n / \r\r
    const sepRegex = /\r?\n\r?\n|\r\r/

    // 包装 onDone/onError，收到终止事件时设置标记
    const wrappedOnDone: typeof onDone = (data) => {
      terminated = true
      onDone(data)
    }
    const wrappedOnError: typeof onError = (err) => {
      terminated = true
      onError(err)
    }

    const dispatchEvent = (eventType: string, payload: Record<string, unknown>) => {
      if (eventType === 'step') {
        onStep({
          step_id: String(payload.step_id ?? ''),
          status: String(payload.status ?? ''),
          output: payload.output,
          time_ms: typeof payload.time_ms === 'number' ? payload.time_ms : undefined,
          error: typeof payload.error === 'string' ? payload.error : null,
        })
      } else if (eventType === 'done') {
        wrappedOnDone({
          status: String(payload.status ?? ''),
          total_time_ms: typeof payload.total_time_ms === 'number' ? payload.total_time_ms : 0,
          steps_result: (payload.steps_result as Record<string, unknown>) ?? {},
        })
      } else if (eventType === 'error') {
        wrappedOnError(String(payload.error ?? payload.message ?? '执行失败'))
      } else if (eventType === 'start') {
        // start 事件：回调 run_id（调试模式前端据此调用步进接口）
        options?.onStart?.({
          run_id: typeof payload.run_id === 'string' ? payload.run_id : undefined,
          workflow_id: typeof payload.workflow_id === 'string' ? payload.workflow_id : undefined,
        })
      } else if (eventType === 'step_token') {
        // B2: LLM 流式 token 增量,回调 stepId + delta 供调用方累积显示
        const stepId = typeof payload.step_id === 'string' ? payload.step_id : ''
        const delta = typeof payload.delta === 'string' ? payload.delta : ''
        if (stepId) options?.onStepToken?.(stepId, delta)
      }
    }

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        let match: RegExpExecArray | null
        while ((match = sepRegex.exec(buffer)) !== null) {
          const rawEvent = buffer.slice(0, match.index)
          buffer = buffer.slice(match.index + match[0].length)
          if (!rawEvent) continue
          // 解析单个 SSE 事件块
          let eventType = 'message'
          const dataLines: string[] = []
          for (const line of rawEvent.split(/\r?\n/)) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim()
            } else if (line.startsWith('data:')) {
              dataLines.push(line.slice(5).replace(/^ /, ''))
            }
          }
          const dataLine = dataLines.join('\n')
          if (!dataLine) continue
          let payload: Record<string, unknown>
          try {
            payload = JSON.parse(dataLine)
          } catch {
            continue
          }
          dispatchEvent(eventType, payload)
        }
      }
      // 流结束后 flush decoder 并处理残留 buffer
      buffer += decoder.decode()
      if (buffer.trim()) {
        let eventType = 'message'
        const dataLines: string[] = []
        for (const line of buffer.split(/\r?\n/)) {
          if (line.startsWith('event:')) {
            eventType = line.slice(6).trim()
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).replace(/^ /, ''))
          }
        }
        const dataLine = dataLines.join('\n')
        if (dataLine) {
          try {
            const payload = JSON.parse(dataLine)
            dispatchEvent(eventType, payload)
          } catch {
            // 忽略无法解析的残留数据
          }
        }
      }
      // 流正常结束但未收到 done/error 事件：视为异常中断，通知调用方
      if (!terminated && !controller.signal.aborted) {
        onError('流式执行连接已关闭，未收到完成事件')
      }
    } catch (err) {
      // 主动中止时不触发 onError
      if (!controller.signal.aborted && !terminated) {
        onError(err instanceof Error ? err.message : '读取流式响应失败')
      }
    } finally {
      clearTimeout(timeoutId)
    }
  })()

  return controller
}
