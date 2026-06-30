// A4: 订阅 WebSocket 审批事件 hook
// - 挂载时连接 wsClient(全局单例,多次挂载共享一个连接)
// - 收到 workflow:paused / workflow:resumed 事件时触发回调
// - 卸载时仅取消订阅,不关闭全局连接(供其他组件继续使用)
import { useEffect, useRef } from 'react'
import { useToast } from '@/components/ui/Toast'
import { wsClient } from '../services/ws'
import type { WorkflowPausedEvent, WorkflowResumedEvent } from '../services/ws'

interface Options {
  /** 收到审批暂停事件时触发(如刷新历史列表) */
  onPaused?: (event: WorkflowPausedEvent) => void
  /** 收到审批恢复事件时触发(如刷新历史列表) */
  onResumed?: (event: WorkflowResumedEvent) => void
  /** 是否启用 toast 通知(默认 true) */
  enableToast?: boolean
}

/** A4: 订阅 WebSocket 审批事件,收到时 toast 通知 + 触发回调 */
export function useApprovalWebSocket(options: Options = {}) {
  const toast = useToast()
  const { enableToast = true } = options
  const onPausedRef = useRef(options.onPaused)
  const onResumedRef = useRef(options.onResumed)
  onPausedRef.current = options.onPaused
  onResumedRef.current = options.onResumed

  useEffect(() => {
    wsClient.connect()
    const offPaused = wsClient.on('workflow:paused', (payload) => {
      const evt = payload as unknown as WorkflowPausedEvent
      if (enableToast) {
        toast.success(`收到审批请求: ${evt.message || '请审批此步骤以继续执行'}`)
      }
      onPausedRef.current?.(evt)
    })
    const offResumed = wsClient.on('workflow:resumed', (payload) => {
      const evt = payload as unknown as WorkflowResumedEvent
      if (enableToast) {
        toast.success(
          evt.decision === 'approved' ? '审批已通过,工作流继续执行' : '审批已拒绝,工作流已终止'
        )
      }
      onResumedRef.current?.(evt)
    })
    return () => {
      offPaused()
      offResumed()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enableToast])
}
