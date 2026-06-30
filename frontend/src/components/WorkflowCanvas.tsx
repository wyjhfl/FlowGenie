// ReactFlow 可视化工作流画布
import { useMemo, useCallback, useState, useRef, useEffect } from 'react'
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  MarkerType,
  type Node,
  type Edge,
  type NodeChange,
  type Connection,
  type ReactFlowInstance,
  type EdgeProps,
  applyNodeChanges,
  Handle,
  Position,
  BaseEdge,
  EdgeLabelRenderer,
  getSmoothStepPath,
  useReactFlow,
  ReactFlowProvider,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { StepResult, WorkflowEdge, WorkflowStep, Tool } from '../types/workflow'
import { Workflow, GitBranch, Repeat, Wrench, Copy, ClipboardPaste, Trash2, LayoutGrid } from 'lucide-react'
import { motion } from 'framer-motion'
import { EmptyState } from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import { getLayoutedElements } from '@/lib/layout'

// 模块级剪贴板:跨工作流粘贴,刷新后清空可接受
type Clipboard = {
  steps: WorkflowStep[]
  // 相对偏移:以首个节点为原点,粘贴时加固定偏移
  offsets: { x: number; y: number }[]
  // 内部边(from/to 已归一化为 steps 索引)
  internalEdges: { fromIdx: number; toIdx: number; condition?: string }[]
}
let clipboard: Clipboard | null = null

interface Props {
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  onSelectNode: (id: string | null) => void
  nodes: Node[]
  setNodes: React.Dispatch<React.SetStateAction<Node[]>>
  stepResults?: Record<string, StepResult> | null
  onWorkflowChange?: (steps: WorkflowStep[], edges: WorkflowEdge[]) => void
  currentStepId?: string | null
}

// 执行状态对应的颜色（统一使用 HSL token，避免硬编码 hex）
const STATUS_COLOR: Record<string, string> = {
  success: 'hsl(var(--success))',
  failed: 'hsl(var(--destructive))',
  skipped: 'hsl(var(--muted-foreground))',
  running: 'hsl(var(--primary))',
}

// 节点状态徽章：success ✓ / failed ✗ / running spinner / idle 圆点
// 颜色全部走 HSL token；布局由 .step-node-status-badge（globals.css）提供
function StatusBadge({ status }: { status?: StepResult['status'] }) {
  if (!status) return null
  if (status === 'success') {
    return (
      <span
        className="step-node-status-badge bg-success/20 text-success"
        title="成功"
      >
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="3 8 7 12 13 4" />
        </svg>
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <motion.span
        className="step-node-status-badge bg-destructive/20 text-destructive"
        title="失败"
        animate={{ x: [0, -3, 3, -3, 3, 0] }}
        transition={{ duration: 0.4, repeat: Infinity, repeatDelay: 2, ease: 'easeInOut' }}
      >
        <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <line x1="4" y1="4" x2="12" y2="12" />
          <line x1="12" y1="4" x2="4" y2="12" />
        </svg>
      </motion.span>
    )
  }
  if (status === 'running') {
    return (
      <span
        className="step-node-status-badge animate-pulse bg-primary/20 text-primary"
        title="运行中"
      >
        <span className="badge-spinner" />
      </span>
    )
  }
  // skipped / idle：灰色小圆点
  return (
    <span
      className="step-node-status-badge bg-muted text-muted-foreground"
      title="待执行"
    />
  )
}

// 自定义边组件：支持条件标签切换与删除按钮
function CustomEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  style,
}: EdgeProps) {
  const [edgePath, labelX, labelY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  })

  const condition = data?.condition as string | undefined
  const isTrue = condition === 'true'
  const isException = condition === 'exception'
  const isSelected = !!data?.isSelected

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} />
      <EdgeLabelRenderer>
        <div
          style={{
            position: 'absolute',
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: 'all',
          }}
          className="edge-label-container"
        >
          {condition && (
            <button
              className={`edge-condition-label ${
                isException
                  ? 'edge-condition-exception'
                  : isTrue
                  ? 'edge-condition-true'
                  : 'edge-condition-false'
              }`}
              onClick={(e) => {
                e.stopPropagation()
                data?.onToggleCondition?.(data.from, data.to)
              }}
              title="点击切换 true/false/exception"
            >
              {condition}
            </button>
          )}
          {isSelected && (
            <button
              className="edge-delete-btn"
              onClick={(e) => {
                e.stopPropagation()
                data?.onDeleteEdge?.(data.from, data.to)
              }}
              title="删除连线"
            >
              ×
            </button>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}

// 自定义节点组件
interface StepNodeData {
  label: string
  description: string
  tool: string
  toolInfo?: Tool
  params: Record<string, unknown>
  runStatus?: StepResult['status']
  onDelete: (id: string) => void
  stepNumber?: number
  isCurrentStep?: boolean
}
function StepNode({ id, data }: { id: string; data: StepNodeData }) {
  const toolInfo = data.toolInfo
  const isIfElse = data.tool === 'if_else'
  const isLoop = data.tool === 'loop'
  const icon = isIfElse ? <GitBranch className="h-4 w-4" /> : isLoop ? <Repeat className="h-4 w-4" /> : toolInfo?.icon ? <span>{toolInfo.icon}</span> : <Wrench className="h-4 w-4" />
  const status: StepResult['status'] | undefined = data.runStatus
  // 调试模式当前步骤：脉冲边框高亮
  const isCurrent = !!data.isCurrentStep
  // 序号：优先取注入的 stepNumber，否则从 step_id 中解析数字部分
  const stepNumber: number | undefined =
    data.stepNumber ?? (id ? Number(id.split('_').pop()) : undefined)

  const deleteButton = (
    <button
      className="step-node-delete"
      onClick={(e) => {
        e.stopPropagation()
        data.onDelete?.(id)
      }}
      title="删除节点"
    >
      ×
    </button>
  )

  // if_else 节点：标准圆角矩形 + 顶部"分支条件"标签（紫色色条区分）
  if (isIfElse) {
    return (
      <div
        className={cn(
          'step-node step-node-ifelse',
          'border border-border bg-card/80 backdrop-blur-xl transition-colors duration-300',
          isCurrent && 'animate-pulse ring-2 ring-primary'
        )}
        data-tool="if_else"
        data-status={status}
      >
        <Handle type="target" position={Position.Left} />
        {deleteButton}
        {stepNumber != null && !Number.isNaN(stepNumber) && (
          <span className="step-node-number">{stepNumber}</span>
        )}
        <div className="step-node-ifelse-label">分支条件</div>
        <div className="step-node-header bg-gradient-to-b from-primary/20 to-transparent">
          <span className="step-node-icon">{icon}</span>
          <span className="step-node-name">{data.label}</span>
          <StatusBadge status={status} />
        </div>
        <div className="step-node-body">
          <div className="step-node-tool">{toolInfo?.display_name || data.tool}</div>
          <div className="step-node-desc">{data.description}</div>
        </div>
        <Handle type="source" position={Position.Right} />
      </div>
    )
  }

  // loop 节点：循环图标 + 计数提示
  const inputArray = data.params?.input_array
  const loopCount = Array.isArray(inputArray) ? inputArray.length : null
  const hasLoopHint = isLoop && inputArray !== undefined && inputArray !== null

  return (
    <div
      className={cn(
        'step-node',
        'border border-border bg-card/80 backdrop-blur-xl transition-colors duration-300',
        isCurrent && 'animate-pulse ring-2 ring-primary'
      )}
      data-tool={data.tool}
      data-status={status}
    >
      {deleteButton}
      <Handle type="target" position={Position.Left} />
      {stepNumber != null && !Number.isNaN(stepNumber) && (
        <span className="step-node-number">{stepNumber}</span>
      )}
      <div className="step-node-header bg-gradient-to-b from-primary/20 to-transparent">
        <span className="step-node-icon">{icon}</span>
        <span className="step-node-name">{data.label}</span>
        <StatusBadge status={status} />
      </div>
      <div className="step-node-body">
        <div className="step-node-tool">{toolInfo?.display_name || data.tool}</div>
        <div className="step-node-desc">{data.description}</div>
        {hasLoopHint && (
          <div className="step-node-loop-hint">
            {loopCount !== null ? `循环 ${loopCount} 项` : '循环'}
          </div>
        )}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { step: StepNode }
const edgeTypes = { customEdge: CustomEdge }

function WorkflowCanvasInner({
  steps,
  edges,
  onSelectNode,
  nodes,
  setNodes,
  stepResults,
  onWorkflowChange,
  currentStepId,
}: Props) {
  const [selectedEdge, setSelectedEdge] = useState<{ from: string; to: string } | null>(null)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string | null } | null>(null)
  const rfInstanceRef = useRef<ReactFlowInstance | null>(null)
  const { getNodes, screenToFlowPosition, fitView } = useReactFlow()

  // 删除节点：移除节点 + 关联边 + 同步 steps
  const handleDeleteNode = useCallback(
    (nodeId: string) => {
      setNodes((nds) => nds.filter((n) => n.id !== nodeId))
      const newSteps = steps.filter((s) => s.id !== nodeId)
      const newEdges = edges.filter((e) => e.from !== nodeId && e.to !== nodeId)
      onWorkflowChange?.(newSteps, newEdges)
      onSelectNode(null)
    },
    [setNodes, steps, edges, onWorkflowChange, onSelectNode]
  )

  // 删除边
  const handleDeleteEdge = useCallback(
    (from: string, to: string) => {
      const newEdges = edges.filter((e) => !(e.from === from && e.to === to))
      onWorkflowChange?.(steps, newEdges)
      setSelectedEdge(null)
    },
    [edges, steps, onWorkflowChange]
  )

  // 切换 if_else 出边条件 true/false
  const handleToggleCondition = useCallback(
    (from: string, to: string) => {
      const newEdges = edges.map((e) => {
        if (e.from === from && e.to === to) {
          // 三态循环：true → false → exception → true
          if (e.condition === 'true') return { ...e, condition: 'false' }
          if (e.condition === 'false') return { ...e, condition: 'exception' }
          if (e.condition === 'exception') return { ...e, condition: 'true' }
          return { ...e, condition: 'true' } // 无 condition → true
        }
        return e
      })
      onWorkflowChange?.(steps, newEdges)
    },
    [edges, steps, onWorkflowChange]
  )

  // 连线：拖拽 Handle 创建新边
  const onConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return
      // 自环检测：禁止连接到自身
      if (connection.source === connection.target) return
      // 避免重复边
      const exists = edges.some(
        (e) => e.from === connection.source && e.to === connection.target
      )
      if (exists) return
      // 源节点是 if_else 时默认标记 condition
      const sourceNode = nodes.find((n) => n.id === connection.source)
      const isIfElseSource = sourceNode?.data?.tool === 'if_else'
      const newEdge: WorkflowEdge = {
        from: connection.source,
        to: connection.target,
        ...(isIfElseSource ? { condition: 'true' } : {}),
      }
      onWorkflowChange?.(steps, [...edges, newEdge])
    },
    [edges, nodes, steps, onWorkflowChange]
  )

  // 拖入工具创建新节点
  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      const raw = e.dataTransfer.getData('application/reactflow')
      if (!raw) return
      let tool: Tool
      try {
        tool = JSON.parse(raw)
      } catch {
        return
      }
      const instance = rfInstanceRef.current
      // ReactFlow 未渲染时（空画布），使用默认位置
      const position = instance
        ? instance.screenToFlowPosition({ x: e.clientX, y: e.clientY })
        : { x: 100, y: 100 }
      const stepId = `step_${Date.now()}`
      const defaultParams = JSON.parse(JSON.stringify(tool.params_schema || {}))
      const newNode: Node = {
        id: stepId,
        type: 'step',
        position,
        data: {
          label: tool.display_name,
          description: tool.description,
          tool: tool.name,
          toolInfo: tool,
          params: defaultParams,
        },
      }
      setNodes((nds) => nds.concat(newNode))
      const newStep: WorkflowStep = {
        id: stepId,
        name: tool.display_name,
        description: tool.description,
        tool: tool.name,
        params: defaultParams,
        tool_info: tool,
      }
      onWorkflowChange?.([...steps, newStep], edges)
    },
    [setNodes, steps, edges, onWorkflowChange]
  )

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
  }, [])

  const onInit = useCallback((instance: ReactFlowInstance) => {
    rfInstanceRef.current = instance
  }, [])

  // ===== A1: ReactFlow 内置删除回调,同步 steps/edges =====
  const onNodesDelete = useCallback(
    (deletedNodes: Node[]) => {
      if (!deletedNodes.length) return
      const ids = new Set(deletedNodes.map((n) => n.id))
      const newSteps = steps.filter((s) => !ids.has(s.id))
      const newEdges = edges.filter((e) => !ids.has(e.from) && !ids.has(e.to))
      onWorkflowChange?.(newSteps, newEdges)
      onSelectNode(null)
    },
    [steps, edges, onWorkflowChange, onSelectNode]
  )

  const onEdgesDelete = useCallback(
    (deletedEdges: Edge[]) => {
      if (!deletedEdges.length) return
      const del = new Set(deletedEdges.map((e) => `${e.source}->${e.target}`))
      const newEdges = edges.filter((e) => !del.has(`${e.from}->${e.to}`))
      onWorkflowChange?.(steps, newEdges)
      setSelectedEdge(null)
    },
    [steps, edges, onWorkflowChange]
  )

  // ===== A2: 复制/粘贴 =====
  const handleCopy = useCallback(() => {
    const selectedNodes = getNodes().filter((n) => n.selected)
    if (!selectedNodes.length) return
    // 按选中节点顺序记录对应 steps
    const selectedSteps: WorkflowStep[] = []
    const offsets: { x: number; y: number }[] = []
    const baseX = selectedNodes[0].position.x
    const baseY = selectedNodes[0].position.y
    const idToIdx = new Map<string, number>()
    selectedNodes.forEach((n, idx) => {
      const step = steps.find((s) => s.id === n.id)
      if (step) {
        selectedSteps.push(JSON.parse(JSON.stringify(step)))
        offsets.push({ x: n.position.x - baseX, y: n.position.y - baseY })
        idToIdx.set(n.id, idx)
      }
    })
    if (!selectedSteps.length) return
    // 收集内部边(两端均在选中集合内)
    const internalEdges: Clipboard['internalEdges'] = []
    edges.forEach((e) => {
      const fromIdx = idToIdx.get(e.from)
      const toIdx = idToIdx.get(e.to)
      if (fromIdx !== undefined && toIdx !== undefined) {
        internalEdges.push({ fromIdx, toIdx, condition: e.condition })
      }
    })
    clipboard = { steps: selectedSteps, offsets, internalEdges }
  }, [getNodes, steps, edges])

  const handlePaste = useCallback(() => {
    if (!clipboard || !clipboard.steps.length) return
    const now = Date.now()
    // 视口中心作为粘贴原点
    const center = rfInstanceRef.current
      ? screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 })
      : { x: 100, y: 100 }
    // 生成新 id 映射
    const idMap = new Map<number, string>()
    clipboard.steps.forEach((_, idx) => {
      idMap.set(idx, `step_${now}_${idx}`)
    })
    // 构建新 steps 和 nodes
    const newSteps: WorkflowStep[] = clipboard.steps.map((s, idx) => ({
      ...s,
      id: idMap.get(idx)!,
      // 深拷贝 params 避免引用共享
      params: JSON.parse(JSON.stringify(s.params)),
    }))
    const newNodes: Node[] = clipboard.steps.map((s, idx) => ({
      id: idMap.get(idx)!,
      type: 'step',
      position: {
        x: center.x + clipboard!.offsets[idx].x + 40,
        y: center.y + clipboard!.offsets[idx].y + 40,
      },
      data: {
        label: s.name,
        description: s.description,
        tool: s.tool,
        toolInfo: s.tool_info,
        params: JSON.parse(JSON.stringify(s.params)),
      },
    }))
    // 构建新内部边
    const newEdges: WorkflowEdge[] = clipboard.internalEdges.map((ie) => ({
      from: idMap.get(ie.fromIdx)!,
      to: idMap.get(ie.toIdx)!,
      ...(ie.condition ? { condition: ie.condition } : {}),
    }))
    setNodes((nds) => nds.concat(newNodes))
    onWorkflowChange?.([...steps, ...newSteps], [...edges, ...newEdges])
  }, [screenToFlowPosition, setNodes, steps, edges, onWorkflowChange])

  // ===== A4: 自动布局(定义在 rfEdges 之后,见下文) =====

  // ===== A5: 右键菜单 =====
  const onNodeContextMenu = useCallback((e: React.MouseEvent, node: Node) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId: node.id })
  }, [])

  const onPaneContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setContextMenu({ x: e.clientX, y: e.clientY, nodeId: null })
  }, [])

  // 复制/粘贴/撤销/重做快捷键(撤销重做由 App.tsx 处理,此处仅 Ctrl+C/V)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // 输入框中不触发
      const target = e.target as HTMLElement
      if (
        target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable
      ) {
        return
      }
      const isCopy = (e.ctrlKey || e.metaKey) && e.key === 'c' && !e.shiftKey
      const isPaste = (e.ctrlKey || e.metaKey) && e.key === 'v' && !e.shiftKey
      if (isCopy) {
        handleCopy()
      } else if (isPaste) {
        handlePaste()
      } else {
        return
      }
      e.preventDefault()
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleCopy, handlePaste])

  // 构建 ReactFlow edges（注入回调与选中状态、源节点执行状态）
  const rfEdges: Edge[] = useMemo(() => {
    return edges.map((e, i) => {
      const condition = e.condition
      const isTrue = condition === 'true'
      const isException = condition === 'exception'
      const isSelected =
        selectedEdge?.from === e.from && selectedEdge?.to === e.to
      // 源节点执行状态决定边样式：running 紫/failed 红/success 绿/idle 默认或条件色
      const sourceStatus = stepResults?.[e.from]?.status
      let edgeStyle: React.CSSProperties
      let isAnimated = false
      if (sourceStatus === 'running') {
        // 运行中：紫色虚线流动
        edgeStyle = { stroke: 'hsl(var(--primary))', strokeWidth: 2, strokeDasharray: '6 4' }
        isAnimated = true
      } else if (sourceStatus === 'failed') {
        // 失败：红色虚线
        edgeStyle = { stroke: 'hsl(var(--destructive))', strokeWidth: 2, strokeDasharray: '4 4' }
      } else if (sourceStatus === 'success') {
        // 成功：绿色实线
        edgeStyle = { stroke: 'hsl(var(--success))', strokeWidth: 2 }
      } else if (condition) {
        // 空闲且带条件分支：保留条件颜色（橙/绿/红）
        const stroke = isException
          ? 'hsl(var(--warning))'
          : isTrue
          ? 'hsl(var(--success))'
          : 'hsl(var(--destructive))'
        edgeStyle = { stroke, strokeWidth: 2 }
      } else {
        // 默认：低对比 foreground（主题自适应）
        edgeStyle = { stroke: 'hsl(var(--foreground) / 0.2)', strokeWidth: 1.5 }
      }
      return {
        id: `edge-${e.from}-${e.to}-${i}`,
        source: e.from,
        target: e.to,
        type: 'customEdge',
        animated: isAnimated,
        style: edgeStyle,
        data: {
          condition,
          from: e.from,
          to: e.to,
          isSelected,
          status: sourceStatus,
          onDeleteEdge: handleDeleteEdge,
          onToggleCondition: handleToggleCondition,
        },
      }
    })
  }, [edges, selectedEdge, stepResults, handleDeleteEdge, handleToggleCondition])

  // ===== A4: 自动布局(依赖 rfEdges,故定义在其后) =====
  const handleAutoLayout = useCallback(() => {
    if (!nodes.length) return
    const layouted = getLayoutedElements(nodes, rfEdges)
    setNodes(layouted)
    // 布局后自适应视口(延迟以等待 React 渲染)
    setTimeout(() => fitView({ padding: 0.2 }), 50)
  }, [nodes, rfEdges, setNodes, fitView])

  // 将 stepResults、删除回调和执行序号注入到节点的 data 中
  const nodesWithCallbacks = useMemo(() => {
    return nodes.map((n, idx) => ({
      ...n,
      data: {
        ...n.data,
        runStatus: stepResults?.[n.id]?.status,
        onDelete: handleDeleteNode,
        // 序号取节点在画布中的顺序（1 起），覆盖 step_id 为时间戳的情况
        stepNumber: idx + 1,
        // 调试模式当前步骤标记（脉冲高亮）
        isCurrentStep: !!currentStepId && n.id === currentStepId,
      },
    }))
  }, [nodes, stepResults, handleDeleteNode, currentStepId])

  // P1: 节点数 > 50 时启用 onlyRenderVisibleElements,加速大图渲染
  const useVirtualization = nodes.length > 50

  const onNodesChange = useCallback(
    (changes: NodeChange[]) => {
      setNodes((nds) => applyNodeChanges(changes, nds))
    },
    [setNodes]
  )

  return (
    <div className={cn('canvas-wrapper', 'bg-background')} onDrop={onDrop} onDragOver={onDragOver}>
      {steps.length === 0 ? (
        <div className="canvas-empty">
          <EmptyState
            icon={<Workflow size={24} />}
            title="开始创建你的第一个工作流"
            description="在右侧输入需求，AI 将自动生成"
          />
        </div>
      ) : (
        <ReactFlow
          nodes={nodesWithCallbacks}
          edges={rfEdges}
          onNodesChange={onNodesChange}
          nodeTypes={nodeTypes}
          edgeTypes={edgeTypes}
          defaultEdgeOptions={{
            style: { stroke: 'hsl(var(--foreground) / 0.2)', strokeWidth: 1.5 },
            markerEnd: { type: MarkerType.ArrowClosed, color: 'hsl(var(--foreground) / 0.2)' },
          }}
          onNodeClick={(_, node) => {
            onSelectNode(node.id)
            setSelectedEdge(null)
            setContextMenu(null)
          }}
          onEdgeClick={(_, edge) => {
            setSelectedEdge({ from: edge.source, to: edge.target })
          }}
          onPaneClick={() => {
            onSelectNode(null)
            setSelectedEdge(null)
            setContextMenu(null)
          }}
          onConnect={onConnect}
          onInit={onInit}
          // A1: 启用键盘删除
          deleteKeyCode={['Backspace', 'Delete']}
          onNodesDelete={onNodesDelete}
          onEdgesDelete={onEdgesDelete}
          // A5: 右键菜单
          onNodeContextMenu={onNodeContextMenu}
          onPaneContextMenu={onPaneContextMenu}
          // A6: 批量选择 + 网格吸附
          multiSelectionKeyCode={['Shift', 'Meta', 'Control']}
          selectionOnDrag
          panOnDrag={[1]}
          snapToGrid
          snapGrid={[16, 16]}
          fitView
          fitViewOptions={{ padding: 0.2 }}
          minZoom={0.3}
          maxZoom={1.5}
          // P1: 节点 > 50 时仅渲染视口内节点,加速大图
          onlyRenderVisibleElements={useVirtualization}
        >
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="hsl(var(--foreground) / 0.03)" />
          <Controls />
          <MiniMap
            nodeColor={(n) => {
              const status = n.data?.runStatus as StepResult['status'] | undefined
              if (status && STATUS_COLOR[status]) return STATUS_COLOR[status]
              return n.data?.toolInfo?.color || 'hsl(var(--primary))'
            }}
            maskColor="hsl(var(--background) / 0.7)"
          />
          {/* A4: 整理布局浮动按钮 */}
          <div className="absolute right-3 top-3 z-10 flex gap-1">
            <Button
              variant="outline"
              size="icon"
              onClick={handleAutoLayout}
              title="整理布局"
              aria-label="整理布局"
              className="h-8 w-8 bg-card/80 backdrop-blur"
            >
              <LayoutGrid size={14} />
            </Button>
          </div>
        </ReactFlow>
      )}
      {/* A5: 右键菜单 */}
      {contextMenu && (
        <div
          className="fixed z-50 min-w-[140px] rounded-md border bg-popover p-1 shadow-md"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={() => setContextMenu(null)}
        >
          {contextMenu.nodeId ? (
            <>
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
                onClick={() => { handleCopy(); setContextMenu(null) }}
              >
                <Copy size={14} /> 复制
              </button>
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent disabled:opacity-40"
                onClick={() => { handlePaste(); setContextMenu(null) }}
                disabled={!clipboard}
              >
                <ClipboardPaste size={14} /> 粘贴
              </button>
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm text-destructive hover:bg-accent"
                onClick={() => {
                  handleDeleteNode(contextMenu.nodeId!)
                  setContextMenu(null)
                }}
              >
                <Trash2 size={14} /> 删除
              </button>
            </>
          ) : (
            <>
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent disabled:opacity-40"
                onClick={() => { handlePaste(); setContextMenu(null) }}
                disabled={!clipboard}
              >
                <ClipboardPaste size={14} /> 粘贴
              </button>
              <button
                className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
                onClick={() => { handleAutoLayout(); setContextMenu(null) }}
              >
                <LayoutGrid size={14} /> 整理布局
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}

// 导出包裹 ReactFlowProvider 的版本——useReactFlow() 等 hook 必须在 Provider 内才能使用
export function WorkflowCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <WorkflowCanvasInner {...props} />
    </ReactFlowProvider>
  )
}
