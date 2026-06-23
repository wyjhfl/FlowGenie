// 工作流类型定义

/** 工具定义 */
export interface Tool {
  name: string
  display_name: string
  category: string
  description: string
  params_schema: Record<string, unknown>
  icon: string
  color: string
}

/** 工作流步骤 */
export interface WorkflowStep {
  id: string
  name: string
  description: string
  tool: string
  params: Record<string, unknown>
  tool_info?: Tool | null
}

/** 工作流边 */
export interface WorkflowEdge {
  from: string
  to: string
}

/** 解析响应 */
export interface ParseResponse {
  scenario: string
  summary: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  source: 'template' | 'llm' | 'mock'
}

/** 导出响应 */
export interface ExportResponse {
  format: string
  content: string
  filename: string
}

/** 场景模板 */
export interface ScenarioTemplate {
  key: string
  title: string
  description: string
  requirement: string
  icon: string
}
