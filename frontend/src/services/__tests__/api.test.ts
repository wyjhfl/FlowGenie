import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// vi.mock 工厂会被提升到模块顶部执行,普通 const 变量此时未初始化
// 使用 vi.hoisted 确保 mockApi 在 vi.mock 执行前已就绪
const { mockApi } = vi.hoisted(() => ({
  mockApi: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}))

vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => mockApi),
  },
}))

import {
  getDashboardStats,
  compareRuns,
  listWorkflows,
  saveWorkflow,
  getRunHistory,
  exportRunResult,
  exportWorkflowRuns,
  exportDashboardReport,
  cleanupWorkflowRuns,
} from '../api'

describe('API 模块', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('getDashboardStats 传 days 参数并返回数据', async () => {
    const mockData = { total_runs: 5, trend: [], tool_usage: [] }
    mockApi.get.mockResolvedValue({ data: mockData })
    const result = await getDashboardStats(30)
    expect(mockApi.get).toHaveBeenCalledWith('/stats/dashboard', { params: { days: 30 } })
    expect(result).toEqual(mockData)
  })

  it('getDashboardStats 默认 days=7', async () => {
    mockApi.get.mockResolvedValue({ data: {} })
    await getDashboardStats()
    expect(mockApi.get).toHaveBeenCalledWith('/stats/dashboard', { params: { days: 7 } })
  })

  it('compareRuns URL 正确拼接', async () => {
    mockApi.get.mockResolvedValue({ data: { steps: [] } })
    await compareRuns('wf-1', 'run-a', 'run-b')
    expect(mockApi.get).toHaveBeenCalledWith('/workflows/wf-1/runs/run-a/compare/run-b')
  })

  it('listWorkflows 返回工作流数组', async () => {
    const mockList = [{ id: '1', name: 'wf1' }]
    mockApi.get.mockResolvedValue({ data: mockList })
    const result = await listWorkflows()
    expect(mockApi.get).toHaveBeenCalledWith('/workflows')
    expect(result).toEqual(mockList)
  })

  it('saveWorkflow 发送 POST 请求含 body', async () => {
    mockApi.post.mockResolvedValue({ data: { id: 'new-id' } })
    const body = { name: 'test', scenario: 's', summary: 'm', steps: [], edges: [] }
    const result = await saveWorkflow(body)
    expect(mockApi.post).toHaveBeenCalledWith('/workflows', body)
    expect(result).toEqual({ id: 'new-id' })
  })

  it('getRunHistory URL 正确拼接', async () => {
    mockApi.get.mockResolvedValue({ data: [] })
    await getRunHistory('wf-1')
    expect(mockApi.get).toHaveBeenCalledWith('/workflows/wf-1/runs')
  })
})

// === D1/D3 执行结果导出 ===
// exportRunResult / exportWorkflowRuns 直接用 fetch(非 axios),需单独 mock

describe('执行结果导出 (D1/D3)', () => {
  let fetchMock: ReturnType<typeof vi.fn>
  let createObjectURLMock: ReturnType<typeof vi.fn>
  let revokeObjectURLMock: ReturnType<typeof vi.fn>
  let clickSpy: ReturnType<typeof vi.fn>
  let originalFetch: typeof globalThis.fetch
  // 捕获最近创建的 <a> 元素,用于断言 download 文件名
  let lastAnchor: { download: string; click: ReturnType<typeof vi.fn> }

  beforeEach(() => {
    vi.clearAllMocks()
    originalFetch = globalThis.fetch
    fetchMock = vi.fn()
    globalThis.fetch = fetchMock as unknown as typeof globalThis.fetch

    createObjectURLMock = vi.fn(() => 'blob:mock-url')
    revokeObjectURLMock = vi.fn()
    URL.createObjectURL = createObjectURLMock
    URL.revokeObjectURL = revokeObjectURLMock

    clickSpy = vi.fn()
    lastAnchor = { download: '', click: clickSpy }
    // mock document.createElement:对 'a' 返回捕获对象,其他走原生
    const origCreate = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      if (tag === 'a') {
        // 返回一个满足 HTMLAnchorElement 最小契约的对象
        return lastAnchor as unknown as HTMLAnchorElement
      }
      return origCreate(tag)
    })
    vi.spyOn(document.body, 'appendChild').mockImplementation(() => null as never)
    vi.spyOn(document.body, 'removeChild').mockImplementation(() => null as never)
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('exportRunResult 调用新端点 /api/runs/{runId}/export', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['csv']),
      headers: new Headers({ 'Content-Disposition': 'attachment; filename="r1.csv"' }),
    })
    await exportRunResult('r1', 'csv')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/runs/r1/export')
    expect(url).toContain('format=csv')
    expect(clickSpy).toHaveBeenCalled()
  })

  it('exportRunResult 解析 RFC 5987 filename*=UTF-8 中文文件名', async () => {
    // 模拟后端返回的中文文件名(百分比编码)
    const encoded = encodeURIComponent('我的执行.csv')
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['csv']),
      headers: new Headers({
        'Content-Disposition': `attachment; filename="export.csv"; filename*=UTF-8''${encoded}`,
      }),
    })
    await exportRunResult('r1', 'csv')
    expect(createObjectURLMock).toHaveBeenCalled()
    expect(lastAnchor.download).toBe('我的执行.csv')
  })

  it('exportRunResult 无 Content-Disposition 时回退到默认文件名', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['json']),
      headers: new Headers(),
    })
    await exportRunResult('r2', 'json')
    expect(lastAnchor.download).toBe('run_r2.json')
  })

  it('exportRunResult markdown 格式回退文件名用 .md 扩展名', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['md']),
      headers: new Headers(),
    })
    await exportRunResult('r3', 'markdown')
    expect(lastAnchor.download).toBe('run_r3.md')
  })

  it('exportRunResult 响应非 ok 时抛出错误', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 404, headers: new Headers() })
    await expect(exportRunResult('missing', 'json')).rejects.toThrow('导出失败: 404')
  })

  it('exportWorkflowRuns 调用 /api/workflows/{wfId}/runs/export', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['csv']),
      headers: new Headers({ 'Content-Disposition': 'attachment; filename="wf_runs.csv"' }),
    })
    await exportWorkflowRuns('wf-9', 'csv')
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/workflows/wf-9/runs/export')
    expect(url).toContain('format=csv')
    expect(clickSpy).toHaveBeenCalled()
  })

  it('exportWorkflowRuns 响应非 ok 时抛出错误', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 500, headers: new Headers() })
    await expect(exportWorkflowRuns('wf-x', 'csv')).rejects.toThrow('导出失败: 500')
  })

  it('exportDashboardReport 调用 /api/stats/export 并传 days 参数', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['xlsx']),
      headers: new Headers({ 'Content-Disposition': 'attachment; filename="report.xlsx"' }),
    })
    await exportDashboardReport(30)
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('/api/stats/export')
    expect(url).toContain('format=xlsx')
    expect(url).toContain('days=30')
    expect(clickSpy).toHaveBeenCalled()
  })

  it('exportDashboardReport 默认 days=7', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['xlsx']),
      headers: new Headers(),
    })
    await exportDashboardReport()
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('days=7')
  })

  it('exportDashboardReport 响应非 ok 时抛出错误', async () => {
    fetchMock.mockResolvedValue({ ok: false, status: 403, headers: new Headers() })
    await expect(exportDashboardReport(7)).rejects.toThrow('导出失败: 403')
  })

  it('cleanupWorkflowRuns 默认无参数调用 DELETE 端点', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: 3, workflow_id: 'wf-c' }),
      headers: new Headers(),
    })
    const result = await cleanupWorkflowRuns('wf-c')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toContain('/api/workflows/wf-c/runs/cleanup')
    expect(url).not.toContain('?') // 无参数时不带 query
    expect(init.method).toBe('DELETE')
    expect(result).toEqual({ deleted: 3, workflow_id: 'wf-c' })
  })

  it('cleanupWorkflowRuns 传 retentionDays 时拼接 query', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: 1, workflow_id: 'wf-d' }),
      headers: new Headers(),
    })
    await cleanupWorkflowRuns('wf-d', { retentionDays: 7 })
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('retention_days=7')
    expect(url).not.toContain('before=')
  })

  it('cleanupWorkflowRuns 传 before 时拼接 query', async () => {
    fetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({ deleted: 0, workflow_id: 'wf-e' }),
      headers: new Headers(),
    })
    const beforeIso = '2026-01-01T00:00:00Z'
    await cleanupWorkflowRuns('wf-e', { before: beforeIso })
    const url = fetchMock.mock.calls[0][0] as string
    expect(url).toContain('before=')
    expect(url).toContain(encodeURIComponent(beforeIso))
  })

  it('cleanupWorkflowRuns 响应非 ok 时解析 detail 抛错', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 400,
      json: async () => ({ detail: 'before_iso 格式非法' }),
      headers: new Headers(),
    })
    await expect(cleanupWorkflowRuns('wf-x', { before: 'bad' })).rejects.toThrow(
      'before_iso 格式非法'
    )
  })

  it('cleanupWorkflowRuns 响应非 ok 且无 JSON body 时回退默认错误', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => {
        throw new Error('not JSON')
      },
      headers: new Headers(),
    })
    await expect(cleanupWorkflowRuns('wf-y')).rejects.toThrow('清理失败: 500')
  })
})
