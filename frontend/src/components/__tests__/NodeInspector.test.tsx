import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'

// Mock framer-motion(透传 div,jsdom 下动画无意义)
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => {
      const { initial, animate, transition, ...rest } = props
      void initial
      void animate
      void transition
      return <div {...(rest as Record<string, unknown>)}>{children as React.ReactNode}</div>
    },
  },
}))

// Mock API:getTools 返回工具列表,getLLMModels 返回模型列表
vi.mock('../../services/api', () => ({
  getTools: vi.fn(),
  getLLMModels: vi.fn(),
  // A2: NodeInspector 挂载时调用 listWorkflows 加载工作流列表(供 subworkflow 节点下拉);
  // 现有测试不涉及 subworkflow 节点,默认返回空数组即可。clearAllMocks 不清除 mockResolvedValue。
  listWorkflows: vi.fn().mockResolvedValue([]),
}))

import { NodeInspector } from '../NodeInspector'
import { getTools, getLLMModels } from '../../services/api'
import type { Tool } from '../../types/workflow'

const mockGetTools = vi.mocked(getTools)
const mockGetLLMModels = vi.mocked(getLLMModels)

const mockTools: Tool[] = [
  { name: 'llm_summary', display_name: 'LLM 摘要', category: 'AI 处理', description: '摘要', icon: '🧠', color: '#a78bfa', params_schema: { text: '' }, required: ['text'], output_schema: { summary: 'str' } },
  { name: 'http_request', display_name: 'HTTP 请求', category: '数据获取', description: 'HTTP', icon: '🌐', color: '#38bdf8', params_schema: { url: '', method: 'GET' }, required: ['url'], output_schema: {} },
  { name: 'web_scraper', display_name: '网页抓取', category: '数据获取', description: '抓取', icon: '🕷️', color: '#38bdf8', params_schema: { url: '' }, required: ['url'], output_schema: {} },
  { name: 'schedule_trigger', display_name: '定时触发', category: '触发', description: '触发', icon: '⏰', color: '#f59e0b', params_schema: {}, required: [], output_schema: {} },
  { name: 'function_call', display_name: 'Function Calling 智能体', category: 'AI 处理', description: 'Agent', icon: '🤖', color: '#a78bfa', params_schema: { prompt: '', tools: [], max_iterations: 10 }, required: ['prompt', 'tools'], output_schema: {} },
  { name: 'conversation_start', display_name: '创建会话', category: 'AI 处理', description: 'F2 创建会话', icon: '💬', color: '#a78bfa', params_schema: { system_prompt: '', session_id: '', model: '' }, required: ['system_prompt'], output_schema: { session_id: 'str' } },
  { name: 'conversation_continue', display_name: '续聊会话', category: 'AI 处理', description: 'F2 续聊', icon: '💬', color: '#a78bfa', params_schema: { session_id: '', user_message: '', model: '', temperature: 0.3, max_tokens: 2000 }, required: ['session_id', 'user_message'], output_schema: { reply: 'str' } },
  { name: 'conversation_list', display_name: '查看会话历史', category: 'AI 处理', description: 'F2 查看历史', icon: '💬', color: '#a78bfa', params_schema: { session_id: '' }, required: ['session_id'], output_schema: { messages: 'list' } },
  { name: 'object_storage_upload', display_name: '对象存储-上传', category: '数据存储', description: 'C1 上传', icon: '☁️', color: '#10b981', params_schema: { key: '', content: '', content_type: 'application/json' }, required: ['key', 'content'], output_schema: { success: 'bool', key: 'str', size: 'int' } },
  { name: 'object_storage_download', display_name: '对象存储-下载', category: '数据存储', description: 'C1 下载', icon: '☁️', color: '#10b981', params_schema: { key: '', encoding: 'utf-8' }, required: ['key'], output_schema: { content: 'str', size: 'int' } },
  { name: 'object_storage_list', display_name: '对象存储-列举', category: '数据存储', description: 'C1 列举', icon: '☁️', color: '#10b981', params_schema: { prefix: '', limit: 100 }, required: [], output_schema: { items: 'list', count: 'int' } },
  { name: 'pdf_generator', display_name: 'PDF 生成', category: '数据存储', description: 'C2 PDF', icon: '📄', color: '#10b981', params_schema: { path: '', title: '', mode: 'text', text: '', rows: [] }, required: ['path', 'mode'], output_schema: { path: 'str', size: 'int', mode: 'str' } },
  { name: 'excel_write', display_name: 'Excel 写入', category: '数据存储', description: 'C3 写入', icon: '📊', color: '#10b981', params_schema: { path: '', rows: [], sheet_name: 'Sheet1' }, required: ['path', 'rows'], output_schema: { path: 'str', size: 'int', rows_written: 'int' } },
  { name: 'excel_read', display_name: 'Excel 读取', category: '数据存储', description: 'C3 读取', icon: '📊', color: '#10b981', params_schema: { path: '', sheet_name: '', has_header: true, limit: 0 }, required: ['path'], output_schema: { rows: 'list', rows_count: 'int' } },
  { name: 'image_resize', display_name: '图像-调整尺寸', category: '数据存储', description: 'C4 resize', icon: '🖼️', color: '#10b981', params_schema: { input_path: '', output_path: '', width: 800, height: 600, keep_ratio: true }, required: ['input_path', 'output_path', 'width', 'height'], output_schema: { new_size: 'list', size: 'int' } },
  { name: 'image_info', display_name: '图像-信息', category: '数据存储', description: 'C4 info', icon: '🖼️', color: '#10b981', params_schema: { input_path: '' }, required: ['input_path'], output_schema: { width: 'int', height: 'int', format: 'str' } },
  { name: 'embedding', display_name: '文本向量化', category: 'AI 处理', description: 'C5 embed', icon: '🔢', color: '#a78bfa', params_schema: { texts: [], model: '' }, required: ['texts'], output_schema: { vectors: 'list', dim: 'int', count: 'int' } },
  { name: 'vector_store_upsert', display_name: '向量存储-写入', category: 'AI 处理', description: 'C5 upsert', icon: '🗃️', color: '#a78bfa', params_schema: { store_path: '', items: [], model: '' }, required: ['store_path', 'items'], output_schema: { count: 'int', dim: 'int', upserted: 'int' } },
  { name: 'vector_store_search', display_name: '向量存储-检索', category: 'AI 处理', description: 'C5 search', icon: '🔎', color: '#a78bfa', params_schema: { store_path: '', query: '', query_vector: [], top_k: 5, model: '' }, required: ['store_path'], output_schema: { results: 'list', count: 'int', top_k: 'int' } },
  { name: 'vector_store_delete', display_name: '向量存储-删除', category: 'AI 处理', description: 'C5 delete', icon: '🗑️', color: '#a78bfa', params_schema: { store_path: '', ids: [] }, required: ['store_path', 'ids'], output_schema: { deleted: 'int', remaining: 'int' } },
]

describe('NodeInspector F1: Function Calling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('function_call 工具显示可用工具多选列表', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: 'Agent', description: '', tool: 'function_call', params: { prompt: '测试', tools: [] }, tool_info: mockTools[4] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    // 等待工具列表加载
    await waitFor(() => {
      expect(screen.getByText('可用工具')).toBeInTheDocument()
    })
    // 排除触发器和 function_call 自身,应显示 llm_summary/http_request/web_scraper
    // A2: 新增 listWorkflows mock 后微任务时序变化,工具项需用 findByText 等待异步加载完成
    expect(await screen.findByText('HTTP 请求')).toBeInTheDocument()
    expect(screen.getByText('网页抓取')).toBeInTheDocument()
    // 不应显示触发器(定时触发仅在基本信息区显示工具名,不应出现在多选列表的 checkbox 中)
    // 多选列表中不应有 schedule_trigger 的 checkbox label
    const triggerCheckboxes = screen.queryAllByRole('checkbox', { name: /定时触发/ })
    expect(triggerCheckboxes.length).toBe(0)
  })

  it('LLM 工具默认不显示 Function Calling 工具列表(开关关闭)', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '摘要', description: '', tool: 'llm_summary', params: { text: '内容' }, tool_info: mockTools[0] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('启用 Function Calling(智能体模式)')).toBeInTheDocument()
    })
    // 开关未启用时不显示可用工具列表
    expect(screen.queryByText('可用工具')).not.toBeInTheDocument()
  })

  it('LLM 工具勾选 Function Calling 开关后显示工具列表并调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '摘要', description: '', tool: 'llm_summary', params: { text: '内容' }, tool_info: mockTools[0] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('启用 Function Calling(智能体模式)')).toBeInTheDocument()
    })
    // 勾选开关
    const toggle = screen.getByLabelText('启用 Function Calling(智能体模式)')
    fireEvent.click(toggle)
    // onParamsChange 应设置 tools: []
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ tools: [] }))
  })

  it('LLM 工具已启用 FC 时显示已选工具数量', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '摘要', description: '', tool: 'llm_summary', params: { text: '内容', tools: ['http_request', 'web_scraper'] }, tool_info: mockTools[0] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('2 已选')).toBeInTheDocument()
    })
  })

  it('勾选工具复选框调用 onParamsChange 添加工具', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: 'Agent', description: '', tool: 'function_call', params: { prompt: '测试', tools: [] }, tool_info: mockTools[4] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('HTTP 请求')).toBeInTheDocument()
    })
    // 点击 HTTP 请求 的 checkbox(label)
    const httpLabel = screen.getByText('HTTP 请求').closest('label')
    fireEvent.click(httpLabel!)
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ tools: ['http_request'] }))
  })
})

describe('NodeInspector F2: 会话记忆工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('conversation_start 渲染 system_prompt 和 session_id 参数', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '创建会话', description: '', tool: 'conversation_start', params: { system_prompt: '你是客服', session_id: 'cust_001' }, tool_info: mockTools[5] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    // 等待参数标签加载(避免与步骤名/工具名重复文本)
    await waitFor(() => {
      expect(screen.getByText('system_prompt')).toBeInTheDocument()
    })
    // 应显示参数标签 system_prompt 和 session_id
    expect(screen.getByText('session_id')).toBeInTheDocument()
    // 应显示已填入的值
    expect(screen.getByDisplayValue('你是客服')).toBeInTheDocument()
    expect(screen.getByDisplayValue('cust_001')).toBeInTheDocument()
  })

  it('conversation_continue 渲染 session_id 和 user_message 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's2', name: '续聊', description: '', tool: 'conversation_continue', params: { session_id: '{{step_1.session_id}}', user_message: '你好' }, tool_info: mockTools[6] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('续聊会话')).toBeInTheDocument()
    })
    // 应显示必填参数
    expect(screen.getByText('session_id')).toBeInTheDocument()
    expect(screen.getByText('user_message')).toBeInTheDocument()
    // session_id 引用了上一步变量
    expect(screen.getByDisplayValue('{{step_1.session_id}}')).toBeInTheDocument()
  })

  it('conversation_list 仅渲染 session_id 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's3', name: '查看历史', description: '', tool: 'conversation_list', params: { session_id: 'sess_abc' }, tool_info: mockTools[7] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('查看会话历史')).toBeInTheDocument()
    })
    expect(screen.getByText('session_id')).toBeInTheDocument()
    expect(screen.getByDisplayValue('sess_abc')).toBeInTheDocument()
    // 不应有 user_message / system_prompt 等其他参数
    expect(screen.queryByText('user_message')).not.toBeInTheDocument()
    expect(screen.queryByText('system_prompt')).not.toBeInTheDocument()
  })

  it('conversation_start 编辑 system_prompt 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '创建会话', description: '', tool: 'conversation_start', params: { system_prompt: '你是客服' }, tool_info: mockTools[5] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('你是客服')).toBeInTheDocument()
    })
    // 修改 system_prompt 输入框
    const input = screen.getByDisplayValue('你是客服')
    fireEvent.change(input, { target: { value: '你是技术支持' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ system_prompt: '你是技术支持' }))
  })
})

describe('NodeInspector C1: 对象存储工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('object_storage_upload 渲染 key/content/content_type 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '上传文件', description: '', tool: 'object_storage_upload', params: { key: 'reports/2026.json', content: '{{step_1.summary}}', content_type: 'application/json' }, tool_info: mockTools[8] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('对象存储-上传')).toBeInTheDocument()
    })
    // 三个参数均应渲染
    expect(screen.getByText('key')).toBeInTheDocument()
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.getByText('content_type')).toBeInTheDocument()
    // 已填入的值
    expect(screen.getByDisplayValue('reports/2026.json')).toBeInTheDocument()
    expect(screen.getByDisplayValue('{{step_1.summary}}')).toBeInTheDocument()
  })

  it('object_storage_download 渲染 key/encoding 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's2', name: '下载文件', description: '', tool: 'object_storage_download', params: { key: '{{step_1.key}}', encoding: 'utf-8' }, tool_info: mockTools[9] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('对象存储-下载')).toBeInTheDocument()
    })
    expect(screen.getByText('key')).toBeInTheDocument()
    expect(screen.getByText('encoding')).toBeInTheDocument()
    // download 不应有 content/content_type
    expect(screen.queryByText('content')).not.toBeInTheDocument()
    expect(screen.queryByText('content_type')).not.toBeInTheDocument()
  })

  it('object_storage_list 渲染 prefix/limit 参数(无必填)', async () => {
    render(
      <NodeInspector
        step={{ id: 's3', name: '列举文件', description: '', tool: 'object_storage_list', params: { prefix: 'reports/', limit: 50 }, tool_info: mockTools[10] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('对象存储-列举')).toBeInTheDocument()
    })
    expect(screen.getByText('prefix')).toBeInTheDocument()
    expect(screen.getByText('limit')).toBeInTheDocument()
    expect(screen.getByDisplayValue('reports/')).toBeInTheDocument()
  })

  it('object_storage_upload 编辑 key 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '上传', description: '', tool: 'object_storage_upload', params: { key: 'old.json', content: 'data' }, tool_info: mockTools[8] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('old.json')).toBeInTheDocument()
    })
    const input = screen.getByDisplayValue('old.json')
    fireEvent.change(input, { target: { value: 'new.json' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ key: 'new.json' }))
  })
})

describe('NodeInspector C2: PDF 生成工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('pdf_generator 渲染 path/title/mode/text 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '生成 PDF', description: '', tool: 'pdf_generator', params: { path: 'reports/2026.pdf', title: '月报', mode: 'text', text: '正文内容' }, tool_info: mockTools[11] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('PDF 生成')).toBeInTheDocument()
    })
    expect(screen.getByText('path')).toBeInTheDocument()
    expect(screen.getByText('title')).toBeInTheDocument()
    expect(screen.getByText('mode')).toBeInTheDocument()
    expect(screen.getByText('text')).toBeInTheDocument()
    expect(screen.getByDisplayValue('reports/2026.pdf')).toBeInTheDocument()
    expect(screen.getByDisplayValue('月报')).toBeInTheDocument()
    expect(screen.getByDisplayValue('正文内容')).toBeInTheDocument()
  })

  it('pdf_generator 编辑 path 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '生成 PDF', description: '', tool: 'pdf_generator', params: { path: 'old.pdf', mode: 'text', text: 'x' }, tool_info: mockTools[11] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('old.pdf')).toBeInTheDocument()
    })
    const input = screen.getByDisplayValue('old.pdf')
    fireEvent.change(input, { target: { value: 'new.pdf' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ path: 'new.pdf' }))
  })
})

describe('NodeInspector C3: Excel 读写工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('excel_write 渲染 path/rows/sheet_name 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '写入 Excel', description: '', tool: 'excel_write', params: { path: 'data.xlsx', rows: [], sheet_name: 'Sheet1' }, tool_info: mockTools[12] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('Excel 写入')).toBeInTheDocument()
    })
    expect(screen.getByText('path')).toBeInTheDocument()
    expect(screen.getByText('sheet_name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('data.xlsx')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Sheet1')).toBeInTheDocument()
  })

  it('excel_read 渲染 path/sheet_name/has_header/limit 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's2', name: '读取 Excel', description: '', tool: 'excel_read', params: { path: 'input.xlsx', sheet_name: 'Data', has_header: true, limit: 100 }, tool_info: mockTools[13] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('Excel 读取')).toBeInTheDocument()
    })
    expect(screen.getByText('path')).toBeInTheDocument()
    expect(screen.getByText('sheet_name')).toBeInTheDocument()
    expect(screen.getByDisplayValue('input.xlsx')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Data')).toBeInTheDocument()
  })

  it('excel_write 编辑 sheet_name 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '写入', description: '', tool: 'excel_write', params: { path: 'd.xlsx', rows: [['a']], sheet_name: 'OldSheet' }, tool_info: mockTools[12] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('OldSheet')).toBeInTheDocument()
    })
    const input = screen.getByDisplayValue('OldSheet')
    fireEvent.change(input, { target: { value: 'NewSheet' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ sheet_name: 'NewSheet' }))
  })
})

describe('NodeInspector C4: 图像处理工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('image_resize 渲染 input_path/output_path/width/height/keep_ratio 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '调整尺寸', description: '', tool: 'image_resize', params: { input_path: 'in.png', output_path: 'out.png', width: 800, height: 600, keep_ratio: true }, tool_info: mockTools[14] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('图像-调整尺寸')).toBeInTheDocument()
    })
    expect(screen.getByText('input_path')).toBeInTheDocument()
    expect(screen.getByText('output_path')).toBeInTheDocument()
    expect(screen.getByText('width')).toBeInTheDocument()
    expect(screen.getByText('height')).toBeInTheDocument()
    expect(screen.getByDisplayValue('in.png')).toBeInTheDocument()
    expect(screen.getByDisplayValue('out.png')).toBeInTheDocument()
  })

  it('image_info 仅渲染 input_path 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's2', name: '获取信息', description: '', tool: 'image_info', params: { input_path: 'photo.jpg' }, tool_info: mockTools[15] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('图像-信息')).toBeInTheDocument()
    })
    expect(screen.getByText('input_path')).toBeInTheDocument()
    expect(screen.getByDisplayValue('photo.jpg')).toBeInTheDocument()
    // image_info 不应有 output_path/width/height
    expect(screen.queryByText('output_path')).not.toBeInTheDocument()
    expect(screen.queryByText('width')).not.toBeInTheDocument()
  })

  it('image_resize 编辑 width 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '调整', description: '', tool: 'image_resize', params: { input_path: 'in.png', output_path: 'out.png', width: 800, height: 600 }, tool_info: mockTools[14] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('800')).toBeInTheDocument()
    })
    const input = screen.getByDisplayValue('800')
    fireEvent.change(input, { target: { value: '1024' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ width: 1024 }))
  })
})

describe('NodeInspector C5: 向量检索/RAG 工具', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockGetTools.mockResolvedValue(mockTools)
    mockGetLLMModels.mockResolvedValue({ models: ['gpt-4o'], default: 'agnes-flash' })
  })

  it('embedding 渲染 texts/model 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's1', name: '向量化', description: '', tool: 'embedding', params: { texts: ['hello', 'world'], model: 'text-embedding-3-small' }, tool_info: mockTools[16] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('文本向量化')).toBeInTheDocument()
    })
    expect(screen.getByText('texts')).toBeInTheDocument()
    expect(screen.getByText('model')).toBeInTheDocument()
    expect(screen.getByDisplayValue('text-embedding-3-small')).toBeInTheDocument()
  })

  it('vector_store_upsert 渲染 store_path/items/model 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's2', name: '写入向量', description: '', tool: 'vector_store_upsert', params: { store_path: 'vectors/kb.pkl', items: [{ id: 'd1', text: 'x' }], model: '' }, tool_info: mockTools[17] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('向量存储-写入')).toBeInTheDocument()
    })
    expect(screen.getByText('store_path')).toBeInTheDocument()
    expect(screen.getByText('items')).toBeInTheDocument()
    expect(screen.getByDisplayValue('vectors/kb.pkl')).toBeInTheDocument()
  })

  it('vector_store_search 渲染 store_path/query/top_k 参数', async () => {
    render(
      <NodeInspector
        step={{ id: 's3', name: '向量检索', description: '', tool: 'vector_store_search', params: { store_path: 'vectors/kb.pkl', query: '{{trigger_data.question}}', top_k: 5 }, tool_info: mockTools[18] }}
        steps={[]}
        edges={[]}
        onParamsChange={vi.fn()}
      />
    )
    await waitFor(() => {
      expect(screen.getByText('向量存储-检索')).toBeInTheDocument()
    })
    expect(screen.getByText('store_path')).toBeInTheDocument()
    expect(screen.getByText('query')).toBeInTheDocument()
    expect(screen.getByText('top_k')).toBeInTheDocument()
    expect(screen.getByDisplayValue('vectors/kb.pkl')).toBeInTheDocument()
    expect(screen.getByDisplayValue('{{trigger_data.question}}')).toBeInTheDocument()
  })

  it('vector_store_search 编辑 top_k 调用 onParamsChange', async () => {
    const onParamsChange = vi.fn()
    render(
      <NodeInspector
        step={{ id: 's1', name: '检索', description: '', tool: 'vector_store_search', params: { store_path: 'kb.pkl', query: 'foo', top_k: 5 }, tool_info: mockTools[18] }}
        steps={[]}
        edges={[]}
        onParamsChange={onParamsChange}
      />
    )
    await waitFor(() => {
      expect(screen.getByDisplayValue('5')).toBeInTheDocument()
    })
    const input = screen.getByDisplayValue('5')
    fireEvent.change(input, { target: { value: '10' } })
    expect(onParamsChange).toHaveBeenCalledWith('s1', expect.objectContaining({ top_k: 10 }))
  })
})
