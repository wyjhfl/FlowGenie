import { useState, useCallback } from 'react'
import type { Node } from 'reactflow'
import { RequirementInput } from './components/RequirementInput'
import { WorkflowCanvas } from './components/WorkflowCanvas'
import { NodeInspector } from './components/NodeInspector'
import { ExportPanel } from './components/ExportPanel'
import { parseRequirement } from './services/api'
import type { ParseResponse, WorkflowStep } from './types/workflow'

function App() {
  const [loading, setLoading] = useState(false)
  const [workflow, setWorkflow] = useState<ParseResponse | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [error, setError] = useState<string>('')

  // 根据工作流步骤生成 ReactFlow 节点
  const buildNodes = useCallback((steps: WorkflowStep[]): Node[] => {
    const stepMap = new Map(steps.map((s) => [s.id, s]))
    return steps.map((step, idx) => {
      const toolInfo = step.tool_info
      // 垂直排列节点
      const cols = Math.min(steps.length, 3)
      const row = Math.floor(idx / cols)
      const col = idx % cols
      return {
        id: step.id,
        type: 'step',
        position: { x: col * 320, y: row * 180 },
        data: {
          label: step.name,
          description: step.description,
          tool: step.tool,
          toolInfo,
          stepMap,
        },
      }
    })
  }, [])

  const handleParse = async (requirement: string) => {
    setLoading(true)
    setError('')
    try {
      const result = await parseRequirement(requirement)
      setWorkflow(result)
      setNodes(buildNodes(result.steps))
      setSelectedNodeId(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求失败')
      setWorkflow(null)
      setNodes([])
    } finally {
      setLoading(false)
    }
  }

  // 选中的步骤
  const selectedStep = workflow?.steps.find((s) => s.id === selectedNodeId) || null

  return (
    <div className="app">
      <header className="hero">
        <div className="hero-badge">学习工作赛道 · TRAE AI 创造力大赛</div>
        <h1>FlowGenie</h1>
        <p className="hero-subtitle">自然语言驱动的 AI 智能工作流生成器 —— 说需求，自动搭工作流</p>
      </header>

      <main className="main-layout">
        {/* 左侧：输入区 */}
        <aside className="sidebar-left">
          <RequirementInput onParse={handleParse} loading={loading} />
          {error && <div className="error-msg">⚠ {error}</div>}
          {workflow && (
            <div className="workflow-meta">
              <div className="meta-row">
                <span className="badge badge-source">来源: {workflow.source}</span>
                <span className="badge badge-scenario">{workflow.scenario}</span>
              </div>
              <p className="meta-summary">{workflow.summary}</p>
            </div>
          )}
        </aside>

        {/* 中间：可视化画布 */}
        <section className="canvas-section">
          <WorkflowCanvas
            steps={workflow?.steps || []}
            edges={workflow?.edges || []}
            selectedNodeId={selectedNodeId}
            onSelectNode={setSelectedNodeId}
            nodes={nodes}
            setNodes={setNodes}
          />
        </section>

        {/* 右侧：节点详情 */}
        <aside className="sidebar-right">
          <NodeInspector step={selectedStep} />
        </aside>
      </main>

      {/* 底部：导出面板 */}
      <footer className="footer-section">
        <ExportPanel workflow={workflow} />
      </footer>
    </div>
  )
}

export default App
