// 节点参数查看与编辑面板
import { useState, useEffect, useRef } from 'react'
import { Wrench } from 'lucide-react'
import type { WorkflowStep, WorkflowEdge, Tool } from '../types/workflow'
import { getTools, getLLMModels, listWorkflows } from '../services/api'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Label } from '@/components/ui/Label'
import { Badge } from '@/components/ui/Badge'
import { Separator } from '@/components/ui/Separator'
import { Button } from '@/components/ui/Button'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/Select'
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from '@/components/ui/DropdownMenu'

/** 后端返回的工具定义（含 output_schema，前端 Tool 类型未声明该字段） */
interface ToolWithOutput extends Tool {
  output_schema?: Record<string, string>
}

interface Props {
  step: WorkflowStep | null
  steps?: WorkflowStep[]
  edges?: WorkflowEdge[]
  onParamsChange?: (stepId: string, newParams: Record<string, unknown>) => void
}

/** BFS 反向遍历，找到当前节点的所有前序节点（拓扑上可达的上游节点） */
function getPredecessors(
  currentNodeId: string,
  steps: WorkflowStep[],
  edges: WorkflowEdge[]
): WorkflowStep[] {
  const predecessors = new Set<string>()
  const queue = [currentNodeId]
  while (queue.length > 0) {
    const current = queue.shift()!
    for (const edge of edges) {
      if (edge.to === current && !predecessors.has(edge.from)) {
        predecessors.add(edge.from)
        queue.push(edge.from)
      }
    }
  }
  return steps.filter((s) => predecessors.has(s.id))
}

/** 字段类型 → Badge 文案 */
function fieldTypeOf(val: unknown): string {
  if (val === null) return 'object'
  if (Array.isArray(val)) return 'object'
  return typeof val
}

/** 字符串参数编辑器 - 支持在光标位置插入前序节点输出变量 {{step_id.field}} */
function StringParamEditor({
  value,
  onChange,
  predecessors,
  toolMap,
}: {
  value: string
  onChange: (v: string) => void
  predecessors: WorkflowStep[]
  toolMap: Record<string, ToolWithOutput>
}) {
  const [showVarMenu, setShowVarMenu] = useState(false)
  const inputRef = useRef<HTMLInputElement | HTMLTextAreaElement | null>(null)

  const hasPredecessors = predecessors.length > 0

  const insertVar = (stepId: string, field: string) => {
    const varRef = `{{${stepId}.${field}}}`
    const input = inputRef.current
    if (input) {
      const start = input.selectionStart ?? value.length
      const end = input.selectionEnd ?? value.length
      const newValue = value.substring(0, start) + varRef + value.substring(end)
      onChange(newValue)
      // 恢复光标位置到插入内容之后
      setTimeout(() => {
        if (inputRef.current) {
          inputRef.current.selectionStart = inputRef.current.selectionEnd =
            start + varRef.length
          inputRef.current.focus()
        }
      }, 0)
    } else {
      onChange(value + varRef)
    }
    setShowVarMenu(false)
  }

  const isLong = value.length > 60 || value.includes('\n')

  return (
    <div className="flex flex-col gap-1">
      {isLong ? (
        <Textarea
          ref={(el) => {
            inputRef.current = el
          }}
          className="min-h-[80px] text-xs"
          value={value}
          rows={Math.min(6, Math.max(2, value.split('\n').length))}
          onChange={(e) => onChange(e.target.value)}
        />
      ) : (
        <Input
          ref={(el) => {
            inputRef.current = el
          }}
          type="text"
          className="h-8 text-xs"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {hasPredecessors && (
        <DropdownMenu open={showVarMenu} onOpenChange={setShowVarMenu}>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="outline" size="sm" className="h-6 w-fit text-xs" title="插入前序节点变量">
              {'{x}'} 插入变量
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="max-h-72 w-56 overflow-y-auto">
            {predecessors.map((step, stepIdx) => {
              const tool = toolMap[step.tool]
              const outputFields = tool?.output_schema
                ? Object.keys(tool.output_schema)
                : []
              return (
                <div key={step.id}>
                  {stepIdx > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuLabel className="rounded-sm border border-primary/50 ring-1 ring-primary/30 bg-primary/5">
                    {step.name} ({step.id})
                  </DropdownMenuLabel>
                  {outputFields.length === 0 ? (
                    <DropdownMenuItem
                      disabled
                      className="hover:bg-primary/10 hover:text-primary focus:bg-primary/10 focus:text-primary"
                    >
                      无输出字段
                    </DropdownMenuItem>
                  ) : (
                    outputFields.map((field) => (
                      <DropdownMenuItem
                        key={field}
                        onClick={() => insertVar(step.id, field)}
                        className="hover:bg-primary/10 hover:text-primary focus:bg-primary/10 focus:text-primary"
                      >
                        {field}
                      </DropdownMenuItem>
                    ))
                  )}
                </div>
              )
            })}
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  )
}

/** 根据值类型渲染对应的编辑控件 */
function ParamEditor({
  value,
  onChange,
  predecessors,
  toolMap,
}: {
  value: unknown
  onChange: (v: unknown) => void
  predecessors: WorkflowStep[]
  toolMap: Record<string, ToolWithOutput>
}) {
  // 对象或数组：用 textarea 编辑 JSON
  if (typeof value === 'object' && value !== null) {
    return <JsonObjectEditor value={value} onChange={onChange} />
  }

  // 数字
  if (typeof value === 'number') {
    return (
      <Input
        type="number"
        className="h-8 text-xs"
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    )
  }

  // 布尔
  if (typeof value === 'boolean') {
    return (
      <Select value={String(value)} onValueChange={(v) => onChange(v === 'true')}>
        <SelectTrigger className="h-8 text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">true</SelectItem>
          <SelectItem value="false">false</SelectItem>
        </SelectContent>
      </Select>
    )
  }

  // 字符串：使用支持插入前序节点变量的编辑器
  const strVal = String(value ?? '')
  return (
    <StringParamEditor
      value={strVal}
      onChange={(v) => onChange(v)}
      predecessors={predecessors}
      toolMap={toolMap}
    />
  )
}

/** JSON 对象编辑器 - 用户输入时不重新格式化以保持光标位置，外部 value 变化时才同步 */
function JsonObjectEditor({ value, onChange }: { value: unknown; onChange: (v: unknown) => void }) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = useState('')
  // 标记 text 变化是否由用户输入触发，避免用户输入回流导致光标跳转
  const isUserInput = useRef(false)

  // 外部 value 变化时（如切换节点）同步内部 text；用户输入触发的 value 变化不同步以保持光标位置
  useEffect(() => {
    if (isUserInput.current) {
      isUserInput.current = false
      return
    }
    setText(JSON.stringify(value, null, 2))
    setError('')
  }, [value])

  return (
    <div className="flex flex-col gap-1">
      <Textarea
        className="min-h-[80px] text-xs"
        value={text}
        onChange={(e) => {
          isUserInput.current = true
          setText(e.target.value)
          try {
            const parsed = JSON.parse(e.target.value)
            setError('')
            onChange(parsed)
          } catch {
            setError('JSON 格式错误')
          }
        }}
        rows={4}
      />
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  )
}

export function NodeInspector({ step, steps, edges, onParamsChange }: Props) {
  // 工具列表映射：name → tool（含 output_schema），用于展示前序节点输出字段
  const [toolMap, setToolMap] = useState<Record<string, ToolWithOutput>>({})
  // B3: 可用 LLM 模型列表与默认模型(供 LLM 类工具节点选择模型)
  const [llmModels, setLlmModels] = useState<string[]>([])
  const [llmDefaultModel, setLlmDefaultModel] = useState<string>('')
  // A2: 已保存的工作流列表(供 subworkflow 节点选择目标工作流)
  const [workflowList, setWorkflowList] = useState<Array<{ id: string; name: string }>>([])

  // 组件挂载时加载工具列表；后端 /api/tools 返回的字典已包含 output_schema
  useEffect(() => {
    let cancelled = false
    getTools()
      .then((tools) => {
        if (cancelled) return
        const map: Record<string, ToolWithOutput> = {}
        for (const t of tools as ToolWithOutput[]) {
          map[t.name] = t
        }
        setToolMap(map)
      })
      .catch(() => {
        // 加载失败时静默处理：插入变量按钮仍可展示节点，但无输出字段
      })
    // B3: 加载可用 LLM 模型列表(失败时静默,模型下拉退化为默认模型)
    getLLMModels()
      .then((res) => {
        if (cancelled) return
        setLlmModels(res.models)
        setLlmDefaultModel(res.default)
      })
      .catch(() => {
        // 静默处理:模型下拉将在无选项时隐藏
      })
    // A2: 加载已保存的工作流列表(供 subworkflow 节点下拉选择;失败静默)
    listWorkflows()
      .then((list) => {
        if (cancelled) return
        setWorkflowList(list.map((w) => ({ id: w.id, name: w.name })))
      })
      .catch(() => {
        // 静默处理:工作流下拉将在无选项时退化为手动输入
      })
    return () => {
      cancelled = true
    }
  }, [])

  if (!step) {
    return (
      <div className="flex h-full flex-col">
        <div className="shrink-0 border-b border-border p-3">
          <h3 className="text-base font-semibold">节点详情</h3>
        </div>
        <div className="flex min-h-0 flex-1 items-center justify-center p-6">
          <p className="text-center text-sm text-muted-foreground">
            点击节点查看与编辑参数
          </p>
        </div>
      </div>
    )
  }

  const toolInfo = step.tool_info
  const params = step.params || {}
  const toolDisplayName = toolInfo?.display_name || step.tool || '未知工具'
  const toolIcon = toolInfo?.icon
  const toolCategory = toolInfo?.category || '-'
  const toolDescription = toolInfo?.description || '暂无工具说明'
  const editable = !!onParamsChange

  // B3: 判断是否为 LLM 类工具(llm_summary/llm_analysis/llm_review/llm_generate/
  // llm_translate/llm_classify/llm_extract),这些工具支持节点级 model 参数覆盖默认模型
  const isLLMTool = step.tool.startsWith('llm_')
  // F1: function_call 工具自身(Agent 模式)
  const isFunctionCallTool = step.tool === 'function_call'
  // A2: 子流程调用工具(需选择目标工作流)
  const isSubworkflowTool = step.tool === 'subworkflow'
  // F1: LLM 工具是否已启用 Function Calling(params.tools 非空数组)
  const fcEnabled = isLLMTool && Array.isArray(params.tools) && (params.tools as string[]).length > 0
  // 当前已选模型:优先读 params.model,缺省显示后端默认模型(仅用于下拉展示)
  const currentModel = typeof params.model === 'string' ? params.model : ''
  const modelSelectValue = currentModel || llmDefaultModel || '__default__'
  // A2: 当前已选目标工作流 ID(从 params.workflow_id 读取)
  const currentWorkflowId = typeof params.workflow_id === 'string' ? params.workflow_id : ''

  // 计算前序节点（通过 edges 反向 BFS）
  const predecessors =
    steps && edges ? getPredecessors(step.id, steps, edges) : []

  const handleParamChange = (key: string, newVal: unknown) => {
    if (!onParamsChange) return
    onParamsChange(step.id, { ...params, [key]: newVal })
  }

  // B3: LLM 工具切换模型——空字符串表示使用默认模型(清除 params.model)
  const handleModelChange = (v: string) => {
    if (!onParamsChange) return
    if (v === '__default__' || v === llmDefaultModel) {
      // 选择默认模型时移除 model 参数,回退到后端 LLM_MODEL
      const next = { ...params }
      delete next.model
      onParamsChange(step.id, next)
    } else {
      onParamsChange(step.id, { ...params, model: v })
    }
  }

  // F1: LLM 工具启用/禁用 Function Calling
  const handleToggleFC = (enabled: boolean) => {
    if (!onParamsChange) return
    const next = { ...params }
    if (enabled) {
      next.tools = []
    } else {
      delete next.tools
      delete next.max_iterations
    }
    onParamsChange(step.id, next)
  }

  // F1: 切换工具选中状态(function_call 工具与 LLM FC 共用)
  const handleToolToggle = (toolName: string, checked: boolean) => {
    if (!onParamsChange) return
    const current = Array.isArray(params.tools) ? (params.tools as string[]) : []
    const next = checked
      ? [...new Set([...current, toolName])]
      : current.filter((t) => t !== toolName)
    onParamsChange(step.id, { ...params, tools: next })
  }

  // F1: 可供 Function Calling 调用的工具列表(排除触发器和 function_call 自身,避免递归)
  const fcAvailableTools = Object.values(toolMap)
    .filter((t) => !t.name.endsWith('_trigger') && t.name !== 'function_call' && t.name !== 'loop')
    .sort((a, b) => a.display_name.localeCompare(b.display_name))

  // B3/F1: 通用参数迭代时跳过 model 键(LLM 工具)和 tools 键(由专用 UI 处理)
  // A2: subworkflow 的 workflow_id 键也跳过(由专用下拉处理)
  const paramEntries = Object.entries(params).filter(
    ([key]) => !(isLLMTool && key === 'model')
      && !((isLLMTool || isFunctionCallTool) && key === 'tools')
      && !(isSubworkflowTool && key === 'workflow_id')
  )

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border p-3">
        <h3 className="text-base font-semibold">节点详情</h3>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-3">
        {/* 基本信息 */}
        <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
          <span className="text-muted-foreground">步骤名称</span>
          <span className="break-all">{step.name}</span>
          <span className="text-muted-foreground">步骤说明</span>
          <span className="break-all">{step.description}</span>
          <span className="text-muted-foreground">使用工具</span>
          <span className="break-all">
            {toolIcon ? <span>{toolIcon}</span> : <Wrench className="inline h-3.5 w-3.5" />} {toolDisplayName}
          </span>
          <span className="text-muted-foreground">工具分类</span>
          <span>{toolCategory}</span>
          <span className="text-muted-foreground">工具说明</span>
          <span className="break-all text-muted-foreground">{toolDescription}</span>
        </div>

        <Separator className="my-3" />

        {/* 参数配置 */}
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-semibold">参数配置</h4>
          {editable && (
            <span className="text-xs text-muted-foreground">（可编辑）</span>
          )}
        </div>
        {/* B3: LLM 类工具的模型选择下拉(选项来自 /api/credentials/llm-models) */}
        {isLLMTool && (
          <div className="mt-2 flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Label className="text-xs font-medium">模型</Label>
              <Badge variant="outline" className="text-[10px]">string</Badge>
              {!currentModel && llmDefaultModel && (
                <span className="text-[10px] text-muted-foreground">默认: {llmDefaultModel}</span>
              )}
            </div>
            {editable && llmModels.length > 0 ? (
              <Select value={modelSelectValue} onValueChange={handleModelChange}>
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="使用默认模型" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">使用默认模型{llmDefaultModel ? ` (${llmDefaultModel})` : ''}</SelectItem>
                  {llmModels.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <span className="break-all text-xs text-muted-foreground">
                {currentModel || llmDefaultModel || '未配置默认模型'}
              </span>
            )}
          </div>
        )}
        {/* A2: subworkflow 节点的目标工作流选择下拉(选项来自 /api/workflows 已保存工作流) */}
        {isSubworkflowTool && (
          <div className="mt-2 flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <Label className="text-xs font-medium">目标工作流</Label>
              <Badge variant="outline" className="text-[10px]">string</Badge>
              {!currentWorkflowId && (
                <span className="text-[10px] text-destructive">未选择</span>
              )}
            </div>
            {editable && workflowList.length > 0 ? (
              <Select
                value={currentWorkflowId}
                onValueChange={(v) => handleParamChange('workflow_id', v)}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue placeholder="选择目标工作流" />
                </SelectTrigger>
                <SelectContent>
                  {workflowList.map((w) => (
                    <SelectItem key={w.id} value={w.id}>{w.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : (
              <span className="break-all text-xs text-muted-foreground">
                {currentWorkflowId
                  ? workflowList.find((w) => w.id === currentWorkflowId)?.name || currentWorkflowId
                  : workflowList.length === 0
                    ? '暂无已保存工作流,可手动输入 workflow_id'
                    : '未选择目标工作流'}
              </span>
            )}
            <p className="text-[10px] text-muted-foreground">
              子流程嵌套深度上限 5 层,自动检测循环引用
            </p>
          </div>
        )}
        {/* F1: Function Calling 配置区(function_call 工具始终显示,LLM 工具通过开关启用) */}
        {(isFunctionCallTool || isLLMTool) && editable && (
          <div className="mt-3 rounded-md border border-border bg-card/40 p-2">
            {/* LLM 工具显示启用开关;function_call 工具不需要开关(本身即 Agent) */}
            {isLLMTool && (
              <div className="mb-2 flex items-center gap-2">
                <input
                  type="checkbox"
                  id="fc-toggle"
                  checked={fcEnabled}
                  onChange={(e) => handleToggleFC(e.target.checked)}
                  className="h-3.5 w-3.5"
                />
                <Label htmlFor="fc-toggle" className="text-xs font-medium">
                  启用 Function Calling(智能体模式)
                </Label>
              </div>
            )}
            {(isFunctionCallTool || fcEnabled) && (
              <>
                <div className="mb-1 flex items-center gap-2">
                  <Label className="text-xs font-medium">可用工具</Label>
                  <Badge variant="outline" className="text-[10px]">
                    {Array.isArray(params.tools) ? (params.tools as string[]).length : 0} 已选
                  </Badge>
                </div>
                <p className="mb-1.5 text-[10px] text-muted-foreground">
                  LLM 将自主决策调用这些工具,循环推理直到给出最终答案
                </p>
                <div className="max-h-40 overflow-y-auto rounded border border-border bg-background p-1.5">
                  {fcAvailableTools.length === 0 ? (
                    <span className="text-[10px] text-muted-foreground">加载工具列表中...</span>
                  ) : (
                    fcAvailableTools.map((t) => {
                      const selected = Array.isArray(params.tools)
                        ? (params.tools as string[]).includes(t.name)
                        : false
                      return (
                        <label
                          key={t.name}
                          className="flex cursor-pointer items-center gap-1.5 py-0.5 text-xs hover:bg-accent/30 rounded px-1"
                        >
                          <input
                            type="checkbox"
                            checked={selected}
                            onChange={(e) => handleToolToggle(t.name, e.target.checked)}
                            className="h-3 w-3"
                          />
                          <span>{t.icon}</span>
                          <span className="truncate" title={t.description}>{t.display_name}</span>
                          <span className="text-muted-foreground/60 text-[10px]">{t.name}</span>
                        </label>
                      )
                    })
                  )}
                </div>
              </>
            )}
          </div>
        )}
        {paramEntries.length === 0 && !isLLMTool && !isFunctionCallTool ? (
          <p className="mt-2 text-sm text-muted-foreground">该步骤无参数</p>
        ) : paramEntries.length === 0 && (isLLMTool || isFunctionCallTool) ? (
          /* LLM/function_call 工具且除 model/tools 外无其他参数时,不显示"无参数"提示 */
          null
        ) : (
          <div className="mt-2 flex flex-col gap-3">
            {paramEntries.map(([key, val]) => (
              <div key={key} className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <Label className="text-xs font-medium">{key}</Label>
                  <Badge variant="outline" className="text-[10px]">
                    {fieldTypeOf(val)}
                  </Badge>
                </div>
                {editable ? (
                  <ParamEditor
                    value={val}
                    onChange={(v) => handleParamChange(key, v)}
                    predecessors={predecessors}
                    toolMap={toolMap}
                  />
                ) : (
                  <span className="break-all text-xs text-muted-foreground">
                    {typeof val === 'object'
                      ? JSON.stringify(val)
                      : String(val)}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
