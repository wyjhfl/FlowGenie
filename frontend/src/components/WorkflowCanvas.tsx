// ReactFlow 可视化工作流画布
import { useMemo, useCallback } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  type Node,
  type Edge,
  type NodeChange,
  applyNodeChanges,
  Handle,
  Position,
} from 'reactflow'
import 'reactflow/dist/style.css'

interface Props {
  steps: { id: string; name: string; description: string; tool: string; tool_info?: any }[]
  edges: { from: string; to: string }[]
  selectedNodeId: string | null
  onSelectNode: (id: string | null) => void
  nodes: Node[]
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>
}

// 自定义节点组件
function StepNode({ data, selected }: { data: any; selected: boolean }) {
  const toolInfo = data.toolInfo
  const icon = toolInfo?.icon || '🔧'
  const color = toolInfo?.color || '#38bdf8'

  return (
    <div
      className="step-node"
      style={{
        borderColor: selected ? color : 'var(--rule)',
        boxShadow: selected ? `0 0 0 2px ${color}` : 'none',
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div className="step-node-header" style={{ background: color }}>
        <span className="step-node-icon">{icon}</span>
        <span className="step-node-name">{data.label}</span>
      </div>
      <div className="step-node-body">
        <div className="step-node-tool">{toolInfo?.display_name || data.tool}</div>
        <div className="step-node-desc">{data.description}</div>
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { step: StepNode }

export function WorkflowCanvas({
  steps,
  edges,
  onSelectNode,
  nodes,
  setNodes,
}: Props) {
  // 构建 ReactFlow edges
  const rfEdges: Edge[] = useMemo(() => {
    return edges.map((e, i) => ({
      id: `edge-${i}`,
      source: e.from,
      target: e.to,
      type: 'smoothstep',
      animated: true,
      style: { stroke: '#38bdf8', strokeWidth: 2 },
    }))
  }, [edges])

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds))
    },
    [setNodes]
  )

  const onConnect = useCallback(
    (_conn: unknown) => {
      // 连接操作（可选实现）
    },
    []
  )

  return (
    <div className="canvas-wrapper">
      {steps.length === 0 ? (
        <div className="canvas-empty">
          <div className="canvas-empty-icon">🎨</div>
          <p>在左侧输入需求，AI 将自动生成可视化工作流</p>
        </div>
      ) : (
        <ReactFlow
          nodes={nodes}
          edges={rfEdges}
          onNodesChange={onNodesChange}
          onConnect={onConnect}
          nodeTypes={nodeTypes}
          onNodeClick={(_, node) => onSelectNode(node.id)}
          onPaneClick={() => onSelectNode(null)}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={1.5}
        >
          <Background color="#334155" gap={20} />
          <Controls />
          <MiniMap
            nodeColor={(n) => n.data?.toolInfo?.color || '#38bdf8'}
            maskColor="rgba(15, 23, 42, 0.7)"
          />
        </ReactFlow>
      )}
    </div>
  )
}
