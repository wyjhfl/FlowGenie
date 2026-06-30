// 工作流撤销/重做历史栈(从 App.tsx 抽出,仅记录 workflow 快照,限 50 步)
import { useState, useCallback } from 'react'
import type { Node } from 'reactflow'
import type { ParseResponse, WorkflowStep } from '../types/workflow'

interface HistoryState {
  past: ParseResponse[]
  future: ParseResponse[]
}

interface UseWorkflowHistoryOptions {
  workflow: ParseResponse | null
  setWorkflow: (wf: ParseResponse) => void
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>
  setSelectedNodeId: (id: string | null) => void
  /** 根据步骤线性生成 ReactFlow 节点 */
  buildNodes: (steps: WorkflowStep[]) => Node[]
}

export function useWorkflowHistory({
  workflow,
  setWorkflow,
  setNodes,
  setSelectedNodeId,
  buildNodes,
}: UseWorkflowHistoryOptions) {
  const [history, setHistory] = useState<HistoryState>({ past: [], future: [] })

  /** 记录当前快照到 past(限 50 步),清空 future。在 workflow 即将变更前调用。 */
  const record = useCallback((current: ParseResponse) => {
    setHistory((h) => ({ past: [...h.past, current].slice(-50), future: [] }))
  }, [])

  const undo = useCallback(() => {
    setHistory((h) => {
      if (!h.past.length || !workflow) return h
      const prev = h.past[h.past.length - 1]
      const newPast = h.past.slice(0, -1)
      // 当前压入 future
      const newFuture = [workflow, ...h.future].slice(0, 50)
      setWorkflow(prev)
      setNodes(buildNodes(prev.steps))
      setSelectedNodeId(null)
      return { past: newPast, future: newFuture }
    })
  }, [workflow, buildNodes, setWorkflow, setNodes, setSelectedNodeId])

  const redo = useCallback(() => {
    setHistory((h) => {
      if (!h.future.length || !workflow) return h
      const next = h.future[0]
      const newFuture = h.future.slice(1)
      // 当前压入 past
      const newPast = [...h.past, workflow].slice(-50)
      setWorkflow(next)
      setNodes(buildNodes(next.steps))
      setSelectedNodeId(null)
      return { past: newPast, future: newFuture }
    })
  }, [workflow, buildNodes, setWorkflow, setNodes, setSelectedNodeId])

  /** 清空历史(LLM 生成/加载工作流/新建时调用,新基线不可撤销) */
  const reset = useCallback(() => setHistory({ past: [], future: [] }), [])

  return { history, record, undo, redo, reset }
}
