// 自动布局工具:基于 dagre 计算从上到下的拓扑布局
import dagre from 'dagre'
import type { Node, Edge } from 'reactflow'

const NODE_WIDTH = 200
const NODE_HEIGHT = 80

/**
 * 使用 dagre 对节点进行自动布局
 * @param nodes ReactFlow 节点
 * @param edges ReactFlow 边
 * @param direction 布局方向,'TB' 从上到下(默认),'LR' 从左到右
 * @returns 带新 position 的节点数组(id/连接不变)
 */
export function getLayoutedElements(
  nodes: Node[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB'
): Node[] {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({
    rankdir: direction,
    nodesep: 60,
    ranksep: 80,
    marginx: 40,
    marginy: 40,
  })

  nodes.forEach((node) => {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  })
  edges.forEach((edge) => {
    g.setEdge(edge.source, edge.target)
  })

  dagre.layout(g)

  return nodes.map((node) => {
    const nodeWithPosition = g.node(node.id)
    // dagre 返回左上角坐标,ReactFlow 用中心点,需转换
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - NODE_WIDTH / 2,
        y: nodeWithPosition.y - NODE_HEIGHT / 2,
      },
    }
  })
}
