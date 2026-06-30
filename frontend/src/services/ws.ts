// A4: WebSocket 客户端 - 审批事件实时推送
// - 自动重连(指数退避,上限 30s)
// - 事件分发(on/emit)
// - 单例模式,全局共享一个 WS 连接
// SSE 仍用于执行流 token 推送;WebSocket 仅用于审批请求实时通知(避免轮询)。
type EventHandler = (payload: Record<string, unknown>) => void

class WSClient {
  private ws: WebSocket | null = null
  private url: string
  private listeners: Map<string, Set<EventHandler>> = new Map()
  private reconnectAttempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private manuallyClosed = false

  constructor() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    // api_key 可选:生产环境配置了 FLOWGENIE_API_KEY 时需鉴权
    const apiKey = localStorage.getItem('flowgenie-api-key') || ''
    const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : ''
    this.url = `${proto}//${window.location.host}/ws${query}`
  }

  /** 建立 WS 连接(已连接/连接中时跳过) */
  connect() {
    if (this.manuallyClosed) return
    if (
      this.ws &&
      (this.ws.readyState === WebSocket.OPEN ||
        this.ws.readyState === WebSocket.CONNECTING)
    ) {
      return
    }
    try {
      this.ws = new WebSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.ws.onopen = () => {
      this.reconnectAttempts = 0
    }
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg && typeof msg.type === 'string') {
          this.emit(msg.type, msg)
        }
      } catch {
        // 非 JSON 消息忽略
      }
    }
    this.ws.onclose = () => {
      this.ws = null
      if (!this.manuallyClosed) this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      // onclose 会处理重连
    }
  }

  /** 安排重连(指数退避:1s,2s,4s...上限 30s) */
  private scheduleReconnect() {
    if (this.reconnectTimer) return
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, 30000)
    this.reconnectAttempts++
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  /** 订阅事件,返回取消订阅函数 */
  on(event: string, handler: EventHandler): () => void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(handler)
    return () => {
      this.listeners.get(event)?.delete(handler)
    }
  }

  /** 触发事件(分发给所有订阅者,异常不影响其他订阅者) */
  private emit(event: string, payload: Record<string, unknown>) {
    this.listeners.get(event)?.forEach((h) => {
      try {
        h(payload)
      } catch {
        // 忽略单个订阅者异常
      }
    })
  }

  /** 主动关闭连接(不再自动重连) */
  close() {
    this.manuallyClosed = true
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
  }
}

// 全局单例
export const wsClient = new WSClient()

/** 审批暂停事件 payload */
export interface WorkflowPausedEvent {
  type: 'workflow:paused'
  run_id: string
  workflow_id: string
  message: string
  approvers: string[]
  paused_step_id: string
}

/** 审批恢复事件 payload */
export interface WorkflowResumedEvent {
  type: 'workflow:resumed'
  run_id: string
  workflow_id: string
  decision: 'approved' | 'rejected'
}
