// 后端 API 调用封装
import axios from 'axios'
import type {
  ParseResponse,
  ExportResponse,
  Tool,
  RunResult,
  WorkflowStep,
  WorkflowEdge,
} from '../types/workflow'

// 根据环境变量决定 API 基础地址
// Vercel 部署:优先读环境变量;若环境变量未注入(构建缓存/配置错误),回退到生产后端地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://flowgenie-w8xb.onrender.com'

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

/** 解析需求 → 工作流 */
export async function parseRequirement(
  requirement: string,
  useTemplate?: boolean
): Promise<ParseResponse> {
  const body: Record<string, unknown> = { requirement }
  if (useTemplate !== undefined) body.use_template = useTemplate
  const { data } = await api.post<ParseResponse>('/parse', body)
  return data
}

/** 迭代调整工作流 */
export async function refineWorkflow(
  currentWorkflow: { steps: WorkflowStep[]; edges: WorkflowEdge[]; scenario: string; summary: string },
  instruction: string
): Promise<ParseResponse> {
  const { data } = await api.post<ParseResponse>('/parse/refine', {
    current_workflow: currentWorkflow,
    instruction,
  })
  return data
}

/** 导出工作流 */
export async function exportWorkflow(
  workflow: ParseResponse,
  format: 'trae_skill' | 'trae_skill_yaml' | 'json' | 'python_script' = 'trae_skill'
): Promise<ExportResponse> {
  const { data } = await api.post<ExportResponse>('/export', { workflow, format })
  return data
}

/** 获取工具列表 */
export async function getTools(): Promise<Tool[]> {
  const { data } = await api.get<{ tools: Tool[] }>('/tools')
  return data.tools
}

/** 健康检查 */
export async function healthCheck(): Promise<boolean> {
  try {
    await api.get('/health')
    return true
  } catch {
    return false
  }
}

/** 执行工作流 */
export async function runWorkflow(
  workflow: ParseResponse,
  triggerData?: Record<string, unknown>,
  options?: { workflow_id?: string; on_failure?: string }
): Promise<RunResult> {
  const body: Record<string, unknown> = {
    steps: workflow.steps,
    edges: workflow.edges,
    trigger_data: triggerData ?? null,
  }
  if (options?.workflow_id) body.workflow_id = options.workflow_id
  if (options?.on_failure) body.on_failure = options.on_failure
  const { data } = await api.post<RunResult>('/workflows/run', body, {
    timeout: 120000, // 执行可能耗时较长（LLM 调用等）
  })
  return data
}

// 流式执行工作流（SSE）—— 实现已抽出到 ./sse.ts,此处 re-export 保持向后兼容
// (App.tsx / RunPanel.tsx / 测试 mock 路径 '../../services/api' 无需改动)
export { runWorkflowStream } from './sse'

// ===== 工作流管理 API =====

/** 保存工作流 */
export async function saveWorkflow(data: {
  name: string
  scenario: string
  summary: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  on_failure?: string
}): Promise<{ id: string }> {
  const res = await api.post('/workflows', data)
  return res.data
}

/** 工作流列表 */
export async function listWorkflows(): Promise<
  Array<{
    id: string
    name: string
    scenario: string
    schedule_enabled: boolean
    webhook_id: string | null
    triggers: string[]
    created_at: string
    updated_at: string
  }>
> {
  const res = await api.get('/workflows')
  return res.data
}

/** 工作流详情 */
export async function getWorkflow(id: string): Promise<{
  id: string
  name: string
  scenario: string
  summary: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  on_failure: string
  schedule_enabled: boolean
  webhook_id: string | null
  on_complete_trigger?: Array<{ workflow_id: string; on: string }>
}> {
  const res = await api.get(`/workflows/${id}`)
  return res.data
}

/** 删除工作流 */
export async function deleteWorkflow(id: string): Promise<void> {
  await api.delete(`/workflows/${id}`)
}

/** 更新工作流（支持 name 等字段更新） */
export async function updateWorkflow(
  workflowId: string,
  data: {
    name?: string
    scenario?: string
    summary?: string
    steps?: WorkflowStep[]
    edges?: WorkflowEdge[]
    on_failure?: string
    on_complete_trigger?: Array<{ workflow_id: string; on: string }>
  }
): Promise<void> {
  await api.put(`/workflows/${workflowId}`, data)
}

/** 导入工作流 */
export async function importWorkflow(data: {
  name: string
  steps: WorkflowStep[]
  edges: WorkflowEdge[]
  scenario?: string
  summary?: string
  on_failure?: string
}): Promise<{ id: string }> {
  const res = await api.post('/workflows/import', data)
  return res.data
}

/** 复制工作流 */
export async function duplicateWorkflow(workflowId: string): Promise<{ id: string }> {
  const res = await api.post(`/workflows/${workflowId}/duplicate`)
  return res.data
}

/** 启用调度 */
export async function enableSchedule(id: string): Promise<void> {
  await api.post(`/workflows/${id}/schedule/enable`)
}

/** 禁用调度 */
export async function disableSchedule(id: string): Promise<void> {
  await api.post(`/workflows/${id}/schedule/disable`)
}

/** 定时任务状态项 */
export interface ScheduleStatusItem {
  workflow_id: string
  name: string
  cron: string | null
  next_run_time: string | null
  last_run: {
    id: string
    status: string
    started_at: string | null
    finished_at: string | null
  } | null
}

/** 获取所有已启用调度的工作流定时任务详情 */
export async function getScheduleStatus(): Promise<ScheduleStatusItem[]> {
  const res = await api.get('/workflows/schedule/status')
  return res.data
}

/** 立即触发一次定时工作流执行 */
export async function runScheduleNow(workflowId: string): Promise<{ run_id: string }> {
  const res = await api.post(`/workflows/${workflowId}/schedule/run-now`)
  return res.data
}

// ===== 执行历史 API =====

/** 执行历史列表 */
export async function getRunHistory(workflowId: string): Promise<
  Array<{
    id: string
    trigger_type: string
    status: string
    total_time_ms: number
    started_at: string
    finished_at: string | null
    error: string | null
  }>
> {
  const res = await api.get(`/workflows/${workflowId}/runs`)
  return res.data
}

/** 单次执行详情 */
export async function getRunDetail(
  workflowId: string,
  runId: string
): Promise<{
  id: string
  workflow_id: string
  trigger_type: string
  status: string
  total_time_ms: number
  steps_result: Record<string, unknown>
  started_at: string
  finished_at: string | null
  error: string | null
  logs: Array<{ timestamp: number; level: string; module: string; message: string }>
}> {
  const res = await api.get(`/workflows/${workflowId}/runs/${runId}`)
  return res.data
}

/** 重试结果（新 run 的完整信息） */
export interface RetryRunResult {
  id: string
  workflow_id: string
  trigger_type: string
  status: string
  total_time_ms: number
  steps_result: Record<string, unknown>
  trigger_data: Record<string, unknown> | null
  started_at: string
  finished_at: string | null
  error: string | null
  logs: Array<{ timestamp: number; level: string; module: string; message: string }>
}

/** 重试失败步骤
 *  :param mode: "from_failed"（默认，从第一个失败步骤继续）| "from_start"（从头重新执行）
 */
export async function retryRun(
  workflowId: string,
  runId: string,
  mode: 'from_failed' | 'from_start' = 'from_failed'
): Promise<RetryRunResult> {
  const res = await api.post<RetryRunResult>(
    `/workflows/${workflowId}/runs/${runId}/retry`,
    null,
    { params: { mode }, timeout: 120000 }
  )
  return res.data
}

/** A1: 审批暂停的工作流——批准继续执行后续步骤,拒绝则标记失败
 * :param decision: "approved" | "rejected"
 * :param comment: 审批评论
 */
export async function approveRun(
  workflowId: string,
  runId: string,
  decision: 'approved' | 'rejected',
  comment: string = ''
): Promise<RetryRunResult> {
  const res = await api.post<RetryRunResult>(
    `/workflows/${workflowId}/runs/${runId}/approve`,
    { decision, comment },
    { timeout: 120000 }
  )
  return res.data
}

// ===== 凭证管理 API =====

export interface CredentialItem {
  key: string
  category: string
  display_name: string
  type: 'text' | 'secret'
  configured: boolean
  value: string // 脱敏值
}

/** 获取凭证列表 */
export async function getCredentials(): Promise<CredentialItem[]> {
  const { data } = await api.get('/credentials')
  return data
}

/** 更新凭证 */
export async function updateCredential(key: string, value: string): Promise<void> {
  await api.put('/credentials', { key, value })
}

/** 测试凭证连通性 */
export async function testCredential(key: string): Promise<{ success: boolean; message: string }> {
  const { data } = await api.get('/credentials/test', { params: { key } })
  return data
}

/** B3: 可用 LLM 模型列表(供 NodeInspector 模型下拉) */
export interface LLMModelsResponse {
  models: string[]
  default: string
}

/** B3: 获取可用 LLM 模型列表与默认模型 */
export async function getLLMModels(): Promise<LLMModelsResponse> {
  const { data } = await api.get<LLMModelsResponse>('/credentials/llm-models')
  return data
}

// ===== 用户偏好 API =====

/** 偏好 schema 项(与后端 core/preference_schema.py 对应) */
export interface PreferenceItem {
  key: string
  category: string
  display_name: string
  type: 'text' | 'secret' | 'number' | 'boolean' | 'select'
  default: string
  options: string[] | null
  applicable_tools: Record<string, string[]>
  description: string
}

/** 获取用户偏好 */
export async function getPreferences(): Promise<Record<string, string>> {
  const { data } = await api.get('/preferences')
  return data
}

/** 获取偏好 schema(供前端 schema 驱动渲染) */
export async function getPreferenceSchema(): Promise<PreferenceItem[]> {
  const { data } = await api.get('/preferences/schema')
  return data
}

/** 更新用户偏好（批量） */
export async function updatePreferences(preferences: Record<string, string>): Promise<void> {
  await api.put('/preferences', { preferences })
}

/** 删除单条用户偏好 */
export async function deletePreference(key: string): Promise<void> {
  await api.delete(`/preferences/${encodeURIComponent(key)}`)
}

// ===== 执行统计 Dashboard API =====

/** Dashboard 统计数据 */
export interface DashboardStats {
  total_runs: number
  success_count: number
  failed_count: number
  partial_success_count: number
  success_rate: number
  avg_time_ms: number
  trend: Array<{ date: string; total: number; success: number; failed: number }>
  tool_usage: Array<{ tool: string; count: number }>
  workflow_ranking: Array<{
    workflow_id: string
    name: string
    total: number
    success: number
    failed: number
    success_rate: number
    avg_time_ms: number
  }>
  failure_clusters: Array<{ cluster: string; count: number; sample_error: string }>
  duration_percentiles: { p50: number; p90: number; p95: number; max: number }
  /** B4: LLM token 用量聚合(无 LLM 调用时全 0) */
  token_stats: {
    total_tokens: number
    prompt_tokens: number
    completion_tokens: number
    calls: number
    by_model: Record<string, {
      total_tokens: number
      prompt_tokens: number
      completion_tokens: number
      calls: number
    }>
  }
}

/** 获取执行统计 Dashboard 数据(可指定趋势天数 7/30/90) */
export async function getDashboardStats(days: number = 7): Promise<DashboardStats> {
  const { data } = await api.get<DashboardStats>('/stats/dashboard', { params: { days } })
  return data
}

// ===== 执行对比 API =====

/** 两次执行的步骤级 diff */
export interface RunDiff {
  run1: {
    id: string
    status: string
    total_time_ms: number
    started_at: string | null
    trigger_type: string
  }
  run2: {
    id: string
    status: string
    total_time_ms: number
    started_at: string | null
    trigger_type: string
  }
  steps: Array<{
    step_id: string
    name: string
    status1: string | null
    status2: string | null
    time1: number | null
    time2: number | null
    error1: string | null
    error2: string | null
    changed: boolean
  }>
}

/** 对比同工作流的两次执行,返回步骤级 diff */
export async function compareRuns(
  workflowId: string,
  runId1: string,
  runId2: string
): Promise<RunDiff> {
  const { data } = await api.get<RunDiff>(
    `/workflows/${workflowId}/runs/${runId1}/compare/${runId2}`
  )
  return data
}

// === Workflow Tags & Batch ===

/** 批量操作结果 */
export interface BatchActionResult {
  success: number
  failed: number
  failed_ids: string[]
}

/** 更新工作流（含标签字段，补充原 updateWorkflow 不支持的 tags 参数） */
export async function updateWorkflowWithTags(
  workflowId: string,
  data: {
    name?: string
    scenario?: string
    summary?: string
    steps?: WorkflowStep[]
    edges?: WorkflowEdge[]
    on_failure?: string
    tags?: string[]
  }
): Promise<void> {
  await api.put(`/workflows/${workflowId}`, data)
}

/** 批量操作工作流：enable_schedule / disable_schedule / delete */
export async function batchWorkflows(
  ids: string[],
  action: 'enable_schedule' | 'disable_schedule' | 'delete'
): Promise<BatchActionResult> {
  const res = await api.post<BatchActionResult>('/workflows/batch', { ids, action })
  return res.data
}

/** 工作流列表项（含标签字段） */
export interface WorkflowListItemWithTags {
  id: string
  name: string
  scenario: string
  schedule_enabled: boolean
  webhook_id: string | null
  triggers: string[]
  tags: string[]
  created_at: string
  updated_at: string
}

/** 获取工作流列表（含标签字段，可按标签筛选）。
 *  传入空数组则返回全部工作流；传入标签则后端筛选需全部包含。
 */
export async function listWorkflowsByTags(
  tags: string[] = []
): Promise<WorkflowListItemWithTags[]> {
  const params = tags.length > 0 ? { tags: tags.join(',') } : undefined
  const res = await api.get<WorkflowListItemWithTags[]>('/workflows', { params })
  return res.data
}

// === Workflow Versions ===

/** 获取工作流版本列表（按 version_number 降序） */
export async function listVersions(
  workflowId: string
): Promise<import('../types/workflow').WorkflowVersion[]> {
  const res = await api.get(`/workflows/${workflowId}/versions`)
  return res.data
}

/** 获取单个版本详情 */
export async function getVersion(
  workflowId: string,
  versionId: string
): Promise<import('../types/workflow').WorkflowVersion> {
  const res = await api.get(`/workflows/${workflowId}/versions/${versionId}`)
  return res.data
}

/** 回滚到指定版本（返回更新后的工作流） */
export async function restoreVersion(
  workflowId: string,
  versionId: string
): Promise<import('../types/workflow').Workflow> {
  const res = await api.post(`/workflows/${workflowId}/versions/${versionId}/restore`)
  return res.data
}

// === Run Result Export ===

/** 从 Content-Disposition 头解析文件名,优先 RFC 5987 filename*=UTF-8'' 编码(支持中文),
 *  回退到 ASCII filename="..." */
function parseFilenameFromContentDisposition(cd: string, fallback: string): string {
  if (!cd) return fallback
  // 优先匹配 filename*=UTF-8''<percent-encoded>(RFC 5987,支持中文)
  const starMatch = cd.match(/filename\*=UTF-8''([^;]+)/i)
  if (starMatch) {
    try {
      return decodeURIComponent(starMatch[1])
    } catch {
      return starMatch[1]
    }
  }
  // 回退到 ASCII filename="..."
  const match = cd.match(/filename="?([^";]+)"?/i)
  if (match) return match[1]
  return fallback
}

/** 触发单次执行结果导出下载(format: json/csv/markdown) */
export async function exportRunResult(runId: string, format: 'json' | 'csv' | 'markdown'): Promise<void> {
  const url = `${API_BASE_URL}/api/runs/${runId}/export?format=${format}`
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`导出失败: ${res.status}`)
  }
  const blob = await res.blob()
  const contentDisposition = res.headers.get('Content-Disposition') || ''
  const fallback = `run_${runId}.${format === 'markdown' ? 'md' : format}`
  const filename = parseFilenameFromContentDisposition(contentDisposition, fallback)
  // 用 Blob + a.click 触发下载
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objUrl)
}

/** 触发工作流执行列表导出下载(当前仅支持 csv) */
export async function exportWorkflowRuns(workflowId: string, format: 'csv' = 'csv'): Promise<void> {
  const url = `${API_BASE_URL}/api/workflows/${workflowId}/runs/export?format=${format}`
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`导出失败: ${res.status}`)
  }
  const blob = await res.blob()
  const contentDisposition = res.headers.get('Content-Disposition') || ''
  const fallback = `workflow_${workflowId}_runs.csv`
  const filename = parseFilenameFromContentDisposition(contentDisposition, fallback)
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objUrl)
}

/** 触发 Dashboard 统计报表导出下载(xlsx 多 sheet) */
export async function exportDashboardReport(days: number = 7): Promise<void> {
  const url = `${API_BASE_URL}/api/stats/export?format=xlsx&days=${days}`
  const res = await fetch(url)
  if (!res.ok) {
    throw new Error(`导出失败: ${res.status}`)
  }
  const blob = await res.blob()
  const contentDisposition = res.headers.get('Content-Disposition') || ''
  const fallback = `FlowGenie报表_${days}天.xlsx`
  const filename = parseFilenameFromContentDisposition(contentDisposition, fallback)
  const objUrl = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = objUrl
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(objUrl)
}

/** D4: 手动清理指定工作流的超期已完成执行记录
 *
 * 清理规则:仅清理 success / partial_success 超期记录,failed 始终保留。
 * - before: ISO 8601 截止时间,优先于 retentionDays
 * - retentionDays: 保留天数(覆盖偏好值);0=永久保留
 * - 二者均省略时从偏好 archive_retention_days 读取(默认 90)
 */
export async function cleanupWorkflowRuns(
  workflowId: string,
  options?: { before?: string; retentionDays?: number }
): Promise<{ deleted: number; workflow_id: string }> {
  const params = new URLSearchParams()
  if (options?.before) params.set('before', options.before)
  if (options?.retentionDays !== undefined) params.set('retention_days', String(options.retentionDays))
  const query = params.toString() ? `?${params.toString()}` : ''
  const res = await fetch(
    `${API_BASE_URL}/api/workflows/${workflowId}/runs/cleanup${query}`,
    { method: 'DELETE' }
  )
  if (!res.ok) {
    let detail = `清理失败: ${res.status}`
    try {
      const body = await res.json()
      if (body?.detail) detail = body.detail
    } catch {
      // 响应非 JSON,保留默认错误
    }
    throw new Error(detail)
  }
  return res.json()
}

// === Debug Step Control ===

/** 调试模式：执行下一步 */
export async function stepNext(workflowId: string, runId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}/runs/${runId}/step/next`, { method: 'POST' })
  if (!res.ok) throw new Error(`操作失败: ${res.status}`)
  return res.json()
}

/** 调试模式：全速继续执行（关闭 debug_mode） */
export async function stepContinue(workflowId: string, runId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}/runs/${runId}/step/continue`, { method: 'POST' })
  if (!res.ok) throw new Error(`操作失败: ${res.status}`)
  return res.json()
}

/** 调试模式：中止执行 */
export async function stepAbort(workflowId: string, runId: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${API_BASE_URL}/api/workflows/${workflowId}/runs/${runId}/step/abort`, { method: 'POST' })
  if (!res.ok) throw new Error(`操作失败: ${res.status}`)
  return res.json()
}
