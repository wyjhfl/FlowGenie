// 工作流类型定义
import type { LucideIcon } from 'lucide-react'

/** 工具定义 */
export interface Tool {
  name: string
  display_name: string
  category: string
  description: string
  params_schema: Record<string, unknown>
  required: string[]
  icon: string
  color: string
  output_schema?: Record<string, string>
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
  condition?: string // 条件分支时为 "true" 或 "false"
}

/** 解析响应 */
export interface ParseResponse {
  scenario: string
  summary: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  source: 'template' | 'llm' | 'mock' | 'refine'
  need_clarification?: boolean
  questions?: string[]
  on_failure?: string
}

/** 导出响应 */
export interface ExportResponse {
  format: string
  content: string
  filename: string
  content_type?: string
}

/** 场景模板 */
export interface ScenarioTemplate {
  key: string
  title: string
  description: string
  requirement: string
  icon: LucideIcon
  category: string
}

/** 单步执行结果 */
export interface StepResult {
  output: unknown
  status: 'success' | 'failed' | 'skipped' | 'running'
  error?: string | null
  time_ms?: number
}

/** 工作流执行结果 */
export interface RunResult {
  id?: string
  status: 'success' | 'failed' | 'running' | 'partial_success' | 'aborted' | 'paused'
  steps_result: Record<string, StepResult>
  total_time_ms: number
}

/** 工作流（列表/详情通用，含标签） */
export interface Workflow {
  id: string
  name: string
  scenario: string
  summary: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  on_failure: string
  tags: string[]
  schedule_enabled: boolean
  webhook_id: string | null
  on_complete_trigger?: Array<{ workflow_id: string; on: string }>
  created_at: string
  updated_at: string
}

/** 工作流版本快照 */
export interface WorkflowVersion {
  id: string
  workflow_id: string
  version_number: number
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  summary: string
  on_failure: string
  tags: string[]
  note: string
  created_at: string
}
