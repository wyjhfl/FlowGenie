// SSE 流式执行封装(从 App.tsx 抽出)
// 管理 AbortController 生命周期:run 时持有 controller,abort 中止,卸载时自动中止。
import { useCallback, useEffect, useRef } from 'react'
import type { ParseResponse } from '../types/workflow'
import { runWorkflowStream } from '../services/sse'

type OnStep = Parameters<typeof runWorkflowStream>[1]
type OnDone = Parameters<typeof runWorkflowStream>[2]
type OnError = Parameters<typeof runWorkflowStream>[3]
type RunOptions = Parameters<typeof runWorkflowStream>[4]

export interface SSEStreamApi {
  /** 发起流式执行,返回 AbortController(同时存入 ref 供 abort/卸载清理) */
  run: (
    workflow: ParseResponse,
    onStep: OnStep,
    onDone: OnDone,
    onError: OnError,
    options?: RunOptions
  ) => AbortController
  /** 中止当前流。返回是否确有流被中止(无流时返回 false)。 */
  abort: () => boolean
}

export function useSSEStream(): SSEStreamApi {
  const abortControllerRef = useRef<AbortController | null>(null)

  const abort = useCallback((): boolean => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort()
      abortControllerRef.current = null
      return true
    }
    return false
  }, [])

  // 组件卸载时中止可能仍在进行的 SSE 流,避免状态污染
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort()
        abortControllerRef.current = null
      }
    }
  }, [])

  const run = useCallback(
    (
      workflow: ParseResponse,
      onStep: OnStep,
      onDone: OnDone,
      onError: OnError,
      options?: RunOptions
    ): AbortController => {
      const controller = runWorkflowStream(workflow, onStep, onDone, onError, options)
      abortControllerRef.current = controller
      return controller
    },
    []
  )

  return { run, abort }
}
