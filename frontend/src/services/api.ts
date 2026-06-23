// 后端 API 调用封装
import axios from 'axios'
import type { ParseResponse, ExportResponse, Tool } from '../types/workflow'

// 根据环境变量决定 API 基础地址
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

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

/** 导出工作流 */
export async function exportWorkflow(
  workflow: ParseResponse,
  format: 'trae_skill' | 'trae_skill_yaml' | 'json' = 'trae_skill'
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
