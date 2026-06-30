import { useState, useCallback, useRef, useEffect, lazy, Suspense } from 'react'
import type { Node } from 'reactflow'
import { motion } from 'framer-motion'
import { ChevronDown, ChevronUp, Wrench, TriangleAlert, Workflow, History, Sun, Moon, Info, Plus, Sparkles, LayoutGrid, HelpCircle, Grid3x3, Undo2, Redo2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { WorkflowCanvas } from './components/WorkflowCanvas'
import { NodeInspector } from './components/NodeInspector'
import { RunPanel, type LogEntry } from './components/RunPanel'
import { WorkflowList, type WorkflowListHandle } from './components/WorkflowList'
import { ToolPalette } from './components/ToolPalette'

const ExportPanel = lazy(() => import('./components/ExportPanel').then(m => ({ default: m.ExportPanel })))
const RunHistory = lazy(() => import('./components/RunHistory').then(m => ({ default: m.RunHistory })))
const CredentialPanel = lazy(() => import('./components/CredentialPanel').then(m => ({ default: m.CredentialPanel })))
const PreferencePanel = lazy(() => import('./components/PreferencePanel').then(m => ({ default: m.PreferencePanel })))
const SchedulePanel = lazy(() => import('./components/SchedulePanel').then(m => ({ default: m.SchedulePanel })))
const DashboardPanel = lazy(() => import('./components/DashboardPanel').then(m => ({ default: m.DashboardPanel })))
const DashboardView = lazy(() => import('./components/DashboardView').then(m => ({ default: m.DashboardView })))
const TemplatesView = lazy(() => import('./components/TemplatesView').then(m => ({ default: m.TemplatesView })))
import { SCENARIO_TEMPLATES } from './components/ScenarioTemplates'
import { Sidebar, type SidebarPanel } from '@/components/Sidebar'
import { CommandBar } from '@/components/CommandBar'
import { Command } from '@/components/ui/Command'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/Sheet'
import { Alert, AlertTitle, AlertDescription } from '@/components/ui/Alert'
import { ToastProvider, useToast } from '@/components/ui/Toast'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import {
  parseRequirement,
  refineWorkflow,
  saveWorkflow,
  getWorkflow,
  listWorkflows,
} from './services/api'
import { useWorkflowHistory } from './hooks/useWorkflowHistory'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useSSEStream } from './hooks/useSSEStream'
import type { ParseResponse, WorkflowStep, WorkflowEdge, RunResult, StepResult } from './types/workflow'

function AppContent() {
  const [loading, setLoading] = useState(false)
  const [workflow, setWorkflow] = useState<ParseResponse | null>(null)
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Node[]>([])
  const [error, setError] = useState<string>('')
  const [running, setRunning] = useState(false)
  const [runResult, setRunResult] = useState<RunResult | null>(null)
  // B2: LLM 流式输出——各步骤累积的 token 文本(stepId → 已到达文本),执行完成时清空
  const [streamingTokens, setStreamingTokens] = useState<Record<string, string>>({})
  // 撤销/重做历史栈由 useWorkflowHistory hook 管理(见下方 buildNodes 之后)
  const [clarificationQuestions, setClarificationQuestions] = useState<string[]>([])
  const [pendingRequirement, setPendingRequirement] = useState<string>('')
  // 澄清补充答案（配合 clarificationQuestions 弹窗使用）
  const [clarifyAnswer, setClarifyAnswer] = useState('')

  // 三视图状态切换：dashboard / editor / templates（登录后落地 Dashboard）
  const [currentView, setCurrentView] = useState<'dashboard' | 'editor' | 'templates'>('dashboard')
  // 模板使用时传递的需求：切换到 editor 后由 useEffect 触发 handleParse 生成工作流
  const [templateRequirement, setTemplateRequirement] = useState<string>('')

  // 工作流管理状态
  const [currentWorkflowId, setCurrentWorkflowId] = useState<string | null>(null)
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [workflowName, setWorkflowName] = useState('')
  const [saving, setSaving] = useState(false)
  const workflowListRef = useRef<WorkflowListHandle>(null)
  const [showRunHistory, setShowRunHistory] = useState(false)
  const [showCredentials, setShowCredentials] = useState(false)
  const [showPreferences, setShowPreferences] = useState(false)
  const [showSchedule, setShowSchedule] = useState(false)
  const [showDashboard, setShowDashboard] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [onFailure, setOnFailure] = useState('stop')

  // ===== 新增：主题 / 命令面板 / 面板切换 / 折叠 / 浮动抽屉状态 =====
  // 主题状态：从 localStorage 初始化，dark 为默认
  const [theme, setTheme] = useState<'dark' | 'light'>(
    () => (localStorage.getItem('flowgenie-theme') as 'dark' | 'light') || 'dark'
  )
  // ⌘K 命令面板开关
  const [commandOpen, setCommandOpen] = useState(false)
  // sidebar 当前激活面板（用于高亮）
  const [activePanel, setActivePanel] = useState<SidebarPanel>('dashboard')
  // 工具箱浮动抽屉（T 键唤起）
  const [toolPaletteOpen, setToolPaletteOpen] = useState(false)
  // 移动端 inspector 底部 Sheet（<md 时通过底部 tab bar 唤起）
  const [mobileInspectorOpen, setMobileInspectorOpen] = useState(false)
  // 工作流列表浮层（sidebar 'workflows' 触发）
  const [showWorkflowList, setShowWorkflowList] = useState(false)
  // 导出浮层（sidebar 'export' 触发）
  const [showExport, setShowExport] = useState(false)
  // 命令面板所需的工作流列表
  const [workflows, setWorkflows] = useState<Array<{ id: string; name: string; scenario: string }>>([])
  // RunPanel 底部折叠条展开状态（默认收起 48px，展开 240px 显示日志）
  const [runPanelExpanded, setRunPanelExpanded] = useState(false)

  // 全局 Toast 通知
  const toast = useToast()
  // 未保存修改标记：workflow 变更时置 true，保存成功时置 false
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false)
  // 待执行的动作（新建 / 使用模板）：未保存修改时弹 ConfirmDialog 确认后再执行
  const [pendingAction, setPendingAction] = useState<null | 'new' | 'template'>(null)
  const [pendingTemplateReq, setPendingTemplateReq] = useState('')

  // SSE 流式执行:AbortController 生命周期(运行/中止/卸载清理)交由 hook 管理
  const { run: runStream, abort: abortStreamRaw } = useSSEStream()

  // 主题持久化：同步到 documentElement class 与 localStorage
  useEffect(() => {
    document.documentElement.classList.toggle('light', theme === 'light')
    localStorage.setItem('flowgenie-theme', theme)
  }, [theme])

  const handleThemeToggle = useCallback(() => {
    setTheme((t) => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  // 拉取命令面板工作流列表
  const fetchWorkflows = useCallback(async () => {
    try {
      const list = await listWorkflows()
      setWorkflows(list.map((w) => ({ id: w.id, name: w.name, scenario: w.scenario })))
    } catch {
      // 忽略：命令面板列表加载失败不影响主流程
    }
  }, [])

  useEffect(() => {
    fetchWorkflows()
  }, [fetchWorkflows])

  // 命令面板打开时刷新工作流列表
  useEffect(() => {
    if (commandOpen) fetchWorkflows()
  }, [commandOpen, fetchWorkflows])

  // 全局快捷键(⌘K/T/I + 撤销/重做)统一由 useKeyboardShortcuts 注册(见下方 handleUndo/handleRedo 之后)

  // 面板切换：根据 sidebar 选中项打开对应浮层，关闭其他
  const openPanel = useCallback((panel: SidebarPanel) => {
    setShowCredentials(false)
    setShowPreferences(false)
    setShowSchedule(false)
    setShowDashboard(false)
    setShowExport(false)
    setShowRunHistory(false)
    setShowWorkflowList(false)
    switch (panel) {
      case 'workflows':
        setShowWorkflowList(true)
        break
      case 'credentials':
        setShowCredentials(true)
        break
      case 'preferences':
        setShowPreferences(true)
        break
      case 'schedule':
        setShowSchedule(true)
        break
      case 'dashboard-stats':
        setShowDashboard(true)
        break
      case 'export':
        setShowExport(true)
        break
      case 'history':
        setShowRunHistory(true)
        break
    }
  }, [])

  const handlePanelChange = useCallback(
    (panel: SidebarPanel) => {
      setActivePanel(panel)
      // 视图切换：仅切换 currentView，不打开任何浮层
      if (panel === 'dashboard' || panel === 'editor' || panel === 'templates') {
        setSelectedNodeId(null)
        setCurrentView(panel)
        return
      }
      // 功能图标：打开对应浮层（保持现有行为）
      openPanel(panel)
    },
    [openPanel]
  )

  // 顶部 CommandBar 刷新：刷新工作流列表 + 命令面板列表
  const handleRefresh = useCallback(() => {
    workflowListRef.current?.refresh()
    fetchWorkflows()
  }, [fetchWorkflows])

  // 中止当前 SSE 流并清理运行状态（将 runResult 标记为 aborted，避免卡在 running）
  const abortStream = useCallback(() => {
    if (abortStreamRaw()) {
      setRunning(false)
      setRunResult((prev) => (prev ? { ...prev, status: 'aborted' as RunResult['status'] } : prev))
    }
  }, [abortStreamRaw])

  // 根据工作流步骤生成 ReactFlow 节点（线性从左到右排列）
  const buildNodes = useCallback((steps: WorkflowStep[]): Node[] => {
    return steps.map((step, idx) => ({
      id: step.id,
      type: 'step',
      position: { x: idx * 300, y: 0 },
      data: {
        label: step.name,
        description: step.description,
        tool: step.tool,
        toolInfo: step.tool_info,
        params: step.params,
      },
    }))
  }, [])

  // 撤销/重做历史栈(抽出到 useWorkflowHistory hook):record 记录快照,undo/redo/reset 操作历史
  const {
    history,
    record: recordHistory,
    undo: handleUndo,
    redo: handleRedo,
    reset: resetHistory,
  } = useWorkflowHistory({ workflow, setWorkflow, setNodes, setSelectedNodeId, buildNodes })

  // 全局键盘快捷键(⌘K/T/I + 撤销/重做)统一由 useKeyboardShortcuts 注册
  useKeyboardShortcuts({
    onOpenCommandPalette: () => setCommandOpen(true),
    onToggleToolPalette: () => setToolPaletteOpen((o) => !o),
    onToggleMobileInspector: () => setMobileInspectorOpen((o) => !o),
    onUndo: handleUndo,
    onRedo: handleRedo,
  })

  // 画布增删节点/边时同步更新 workflow 与 nodes（保持已有节点位置，新增节点用默认位置）
  // 同时记录历史快照供撤销/重做
  const handleWorkflowChange = useCallback(
    (newSteps: WorkflowStep[], newEdges: WorkflowEdge[]) => {
      if (!workflow) return
      setHasUnsavedChanges(true)
      // 记录当前快照到 past(限 50 步),清空 future
      recordHistory(workflow)
      setWorkflow({ ...workflow, steps: newSteps, edges: newEdges })
      setNodes((prevNodes) => {
        const existingIds = new Set(prevNodes.map((n) => n.id))
        const newNodes = newSteps
          .filter((s) => !existingIds.has(s.id))
          .map((s, idx) => ({
            id: s.id,
            type: 'step',
            position: { x: (prevNodes.length + idx) * 300, y: 0 },
            data: {
              label: s.name,
              description: s.description,
              tool: s.tool,
              toolInfo: s.tool_info,
              params: s.params,
            },
          }))
        const keptNodes = prevNodes.filter((n) => newSteps.some((s) => s.id === n.id))
        return [...keptNodes, ...newNodes]
      })
    },
    [workflow, recordHistory]
  )

  const handleParse = useCallback(async (requirement: string) => {
    // 重新生成时中止可能仍在进行的执行流，并清空日志
    abortStream()
    setLogs([])
    setLoading(true)
    setError('')
    setRunResult(null) // 重新生成时清空上次执行结果
    try {
      if (workflow) {
        // 迭代调整模式：基于现有工作流按指令调整
        const result = await refineWorkflow(
          {
            steps: workflow.steps,
            edges: workflow.edges,
            scenario: workflow.scenario,
            summary: workflow.summary,
          },
          requirement
        )
        setWorkflow(result)
        setNodes(buildNodes(result.steps))
        setSelectedNodeId(null)
        resetHistory() // A3: LLM 生成新基线,清空历史
        // 迭代模式下不处理 clarification
      } else {
        // 初次解析模式
        setCurrentWorkflowId(null) // 新生成的工作流尚未保存
        const result = await parseRequirement(requirement)
        // 需要澄清：不生成工作流，记录问题与原始需求
        if (result.need_clarification && result.questions && result.questions.length > 0) {
          setClarificationQuestions(result.questions)
          setPendingRequirement(requirement)
          setWorkflow(null)
          setNodes([])
          setSelectedNodeId(null)
          return
        }
        // 正常生成：清空澄清状态
        setClarificationQuestions([])
        setPendingRequirement('')
        setWorkflow(result)
        setNodes(buildNodes(result.steps))
        setSelectedNodeId(null)
        resetHistory() // A3: LLM 生成新基线,清空历史
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : '请求失败')
      // 迭代模式失败时保留原工作流，仅初次解析失败时清空
      if (!workflow) {
        setWorkflow(null)
        setNodes([])
      }
    } finally {
      setLoading(false)
    }
  }, [workflow, abortStream, buildNodes, resetHistory])

  // 澄清补充提交：拼接原始需求与补充答案后重新生成
  const handleClarificationSubmit = (answers: string) => {
    setClarificationQuestions([])
    handleParse(`${pendingRequirement} ${answers}`)
  }

  // 执行工作流（流式 SSE，实时更新结果与日志）
  const handleRun = () => {
    if (!workflow) return
    if (running) return // 防重：避免重复触发执行
    setRunning(true)
    setError('')
    setRunResult(null)
    setLogs([])
    setStreamingTokens({}) // B2: 清空上次流式 token 残留
    runStream(
      workflow,
      // onStep: 每步完成时增量更新结果与日志（临时状态用 running）
      (data) => {
        setRunResult((prev) => ({
          status: 'running',
          steps_result: {
            ...(prev?.steps_result || {}),
            [data.step_id]: {
              output: data.output,
              status: data.status as StepResult['status'],
              error: data.error,
              time_ms: data.time_ms,
            },
          },
          total_time_ms: prev?.total_time_ms || 0,
        }))
        // running 状态只更新步骤状态，不添加完成日志
        if (data.status === 'running') return
        // B2: 步骤完成时清除该步骤的流式 token(切换为完整输出显示)
        setStreamingTokens((prev) => {
          if (!(data.step_id in prev)) return prev
          const next = { ...prev }
          delete next[data.step_id]
          return next
        })
        setLogs((prev) => [
          ...prev,
          {
            time: new Date().toISOString(),
            step_id: data.step_id,
            event: data.status as 'success' | 'failed' | 'skipped',
            message: data.error || '',
            time_ms: data.time_ms,
          },
        ])
      },
      // onDone: 合并 onStep 已积累的步骤结果，仅更新 status 与 total_time_ms
      (data) => {
        setRunResult((prev) => ({
          status: data.status as RunResult['status'],
          steps_result: {
            ...(prev?.steps_result || {}),
            ...(data.steps_result as Record<string, StepResult>),
          },
          total_time_ms: data.total_time_ms,
        }))
        setStreamingTokens({}) // B2: 执行完成清空流式 token
        setRunning(false)
      },
      // onError
      (errMsg) => {
        setError(errMsg)
        setStreamingTokens({}) // B2: 出错时清空流式 token
        setRunning(false)
      },
      {
        workflow_id: currentWorkflowId || undefined,
        on_failure: onFailure,
        // B2: LLM 流式 token 增量回调,累积到 streamingTokens 状态
        onStepToken: (stepId, delta) => {
          setStreamingTokens((prev) => ({
            ...prev,
            [stepId]: (prev[stepId] || '') + delta,
          }))
        },
      }
    )
  }

  // 参数编辑回调：更新某步骤的参数
  const handleParamsChange = (stepId: string, newParams: Record<string, unknown>) => {
    if (!workflow) return
    setWorkflow({
      ...workflow,
      steps: workflow.steps.map((s) =>
        s.id === stepId ? { ...s, params: newParams } : s
      ),
    })
    // 同步更新画布节点的 data.params，保持节点显示与状态一致
    setNodes((prev) =>
      prev.map((n) =>
        n.id === stepId ? { ...n, data: { ...n.data, params: newParams } } : n
      )
    )
  }

  // 保存工作流
  const handleSave = async () => {
    if (!workflow || !workflowName.trim()) return
    setSaving(true)
    setError('')
    try {
      const res = await saveWorkflow({
        name: workflowName.trim(),
        scenario: workflow.scenario,
        summary: workflow.summary,
        steps: workflow.steps,
        edges: workflow.edges,
        on_failure: workflow.on_failure || 'stop',
      })
      setCurrentWorkflowId(res.id)
      setShowSaveDialog(false)
      setWorkflowName('')
      setHasUnsavedChanges(false)
      workflowListRef.current?.refresh() // 刷新侧栏列表
      fetchWorkflows() // 同步命令面板列表
      toast.success('保存成功')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '保存失败'
      setError(msg)
      toast.error(msg)
    } finally {
      setSaving(false)
    }
  }

  // 加载已保存的工作流到画布
  const handleLoadWorkflow = async (id: string) => {
    // 加载新工作流时中止可能仍在进行的执行流，并清空日志
    abortStream()
    setLogs([])
    setLoading(true)
    setError('')
    setRunResult(null)
    try {
      const detail = await getWorkflow(id)
      const loaded: ParseResponse = {
        scenario: detail.scenario,
        summary: detail.summary,
        steps: detail.steps,
        edges: detail.edges,
        on_failure: detail.on_failure,
        source: 'llm',
      }
      setWorkflow(loaded)
      setNodes(buildNodes(detail.steps))
      setSelectedNodeId(null)
      setCurrentWorkflowId(id)
      setClarificationQuestions([])
      setPendingRequirement('')
      setHasUnsavedChanges(false)
      resetHistory() // A3: 加载工作流新基线,清空历史
      toast.success('工作流已加载')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '加载失败'
      setError(msg)
      toast.error(msg)
    } finally {
      setLoading(false)
    }
  }

  // 侧栏删除后通知：若当前工作流被删则清空画布与状态
  const handleListRefresh = (deletedId?: string) => {
    if (deletedId && deletedId === currentWorkflowId) {
      setCurrentWorkflowId(null)
      setWorkflow(null)
      setNodes([])
      setSelectedNodeId(null)
    }
  }

  // ===== DashboardView / TemplatesView 回调 =====
  // 打开已有工作流：加载 + 切换到 editor
  const handleOpenWorkflow = async (id: string) => {
    await handleLoadWorkflow(id)
    setCurrentView('editor')
  }

  // 实际执行新建：清空画布 + 切换到 editor
  const doNewWorkflow = () => {
    abortStream()
    setWorkflow(null)
    setNodes([])
    setCurrentWorkflowId(null)
    setSelectedNodeId(null)
    setClarificationQuestions([])
    setPendingRequirement('')
    setRunResult(null)
    setError('')
    setLogs([])
    setHasUnsavedChanges(false)
    resetHistory() // A3: 新建工作流,清空历史
    setCurrentView('editor')
  }

  // 新建空白工作流：未保存修改时先弹 ConfirmDialog 确认
  const handleNewWorkflow = () => {
    if (hasUnsavedChanges && currentView === 'editor') {
      setPendingAction('new')
      return
    }
    doNewWorkflow()
  }

  // 浏览模板：切换到 templates 视图
  const handleBrowseTemplates = () => {
    setCurrentView('templates')
  }

  // 实际执行使用模板：清空当前工作流 + 切换到 editor + 触发 handleParse 生成
  const doUseTemplate = (requirement: string) => {
    abortStream()
    setWorkflow(null)
    setNodes([])
    setCurrentWorkflowId(null)
    setSelectedNodeId(null)
    setClarificationQuestions([])
    setPendingRequirement('')
    setRunResult(null)
    setError('')
    setLogs([])
    setHasUnsavedChanges(false)
    setTemplateRequirement(requirement)
    setCurrentView('editor')
  }

  // 使用模板：未保存修改时先弹 ConfirmDialog 确认
  const handleUseTemplate = (requirement: string) => {
    if (hasUnsavedChanges && currentView === 'editor') {
      setPendingAction('template')
      setPendingTemplateReq(requirement)
      return
    }
    doUseTemplate(requirement)
  }

  // 模板使用：templateRequirement 非空时触发 handleParse 生成工作流
  // （确保 workflow 已清空，走初次解析模式而非 refine）
  useEffect(() => {
    if (templateRequirement) {
      handleParse(templateRequirement)
      setTemplateRequirement('')
    }
  }, [templateRequirement, handleParse])

  // 选中的步骤
  const selectedStep = workflow?.steps.find((s) => s.id === selectedNodeId) || null

  const openSaveDialog = () => {
    setWorkflowName(workflow?.scenario || '')
    setShowSaveDialog(true)
  }

  // Hero 区"描述需求让 AI 生成"按钮：聚焦 CommandBar 内嵌输入框（focus 触发浮层展开）
  const focusCommandBar = useCallback(() => {
    const input = document.querySelector<HTMLInputElement>('[data-command-bar-input]')
    input?.focus()
  }, [])

  return (
    <div className="flex h-screen bg-background text-foreground">
      {/* 左侧细 sidebar（64px 宽） */}
      <Sidebar
        activePanel={activePanel}
        onPanelChange={handlePanelChange}
        theme={theme}
        onThemeToggle={handleThemeToggle}
      />

      {/* 右侧主区域：顶部 CommandBar + 主内容区 */}
      <div className="flex min-h-0 flex-1 flex-col min-w-0">
        <CommandBar
          workflowName={workflow?.scenario || null}
          viewName={
            currentView === 'dashboard'
              ? '仪表盘'
              : currentView === 'templates'
                ? '模板库'
                : undefined
          }
          onOpenCommand={() => setCommandOpen(true)}
          onRefresh={currentView === 'editor' ? handleRefresh : () => {}}
          onSave={currentView === 'editor' ? openSaveDialog : () => {}}
          saving={saving}
          onParse={currentView === 'editor' ? handleParse : undefined}
          loading={loading}
          refineMode={!!workflow}
          actionsDisabled={currentView !== 'editor'}
        />

        {/* A3: 撤销/重做工具条(仅 editor 视图,消费 history 状态) */}
        {currentView === 'editor' && workflow && (
          <div className="flex items-center gap-1 px-4 py-1 border-b border-border shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleUndo}
              disabled={history.past.length === 0}
              title="撤销 (Ctrl+Z)"
              aria-label="撤销"
            >
              <Undo2 size={14} />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={handleRedo}
              disabled={history.future.length === 0}
              title="重做 (Ctrl+Shift+Z)"
              aria-label="重做"
            >
              <Redo2 size={14} />
            </Button>
          </div>
        )}

        {/* 错误提示条（仅在 editor 视图显示） */}
        {error && currentView === 'editor' && (
          <Alert variant="destructive" className="mx-4 my-2 shrink-0">
            <TriangleAlert className="h-4 w-4" />
            <AlertTitle>错误</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {/* 主内容区：根据 currentView 渲染对应视图 */}
        <main className="flex-1 min-h-0 overflow-hidden">
          {currentView === 'dashboard' && (
            <Suspense fallback={null}>
              <DashboardView
                onOpenWorkflow={handleOpenWorkflow}
                onNewWorkflow={handleNewWorkflow}
                onBrowseTemplates={handleBrowseTemplates}
                onUseTemplate={handleUseTemplate}
              />
            </Suspense>
          )}
          {currentView === 'templates' && (
            <Suspense fallback={null}>
              <TemplatesView onUseTemplate={handleUseTemplate} />
            </Suspense>
          )}
          {currentView === 'editor' && (
            <div className="flex h-full min-h-0 flex-col p-2 pb-20 md:pb-2">
              {/* 画布区（全宽 flex-1） */}
              <div className="relative flex min-h-0 flex-1 flex-col">
                {/* 画布 / Hero 区 */}
                <div className="relative min-h-0 flex-1 overflow-hidden rounded-lg border border-border">
                  {!workflow && !loading ? (
                    // 精简 Hero：虚线方框 + 两个 CTA + 3 个热门模板快捷卡片
                    <div className="flex h-full items-center justify-center overflow-auto p-4">
                      <div className="border-border mx-auto my-auto flex w-full max-w-md flex-col gap-4 rounded-lg border border-dashed p-8">
                        <h2 className="text-2xl font-semibold tracking-tight">从这里开始</h2>
                        <p className="text-sm text-muted-foreground">
                          描述你的需求，让 AI 自动编排工作流；或浏览模板快速开始。
                        </p>
                        <div className="flex flex-wrap gap-2">
                          <Button onClick={focusCommandBar}>
                            <Sparkles className="h-4 w-4" />
                            描述需求让 AI 生成
                          </Button>
                          <Button variant="outline" onClick={() => setCurrentView('templates')}>
                            <LayoutGrid className="h-4 w-4" />
                            浏览模板
                          </Button>
                        </div>
                        {/* 3 个热门模板快捷卡片横排 */}
                        <div className="mt-2 grid grid-cols-3 gap-2">
                          {SCENARIO_TEMPLATES.slice(0, 3).map((t) => (
                            <button
                              key={t.key}
                              type="button"
                              onClick={() => handleUseTemplate(t.requirement)}
                              className="border-border flex flex-col items-center gap-1 rounded-md border p-3 text-center transition-colors hover:border-primary hover:bg-accent"
                            >
                              <t.icon className="h-7 w-7 text-primary" />
                              <span className="text-xs font-medium">{t.title}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    </div>
                  ) : (
                    <WorkflowCanvas
                      steps={workflow?.steps || []}
                      edges={workflow?.edges || []}
                      onSelectNode={setSelectedNodeId}
                      nodes={nodes}
                      setNodes={setNodes}
                      stepResults={runResult?.steps_result || null}
                      onWorkflowChange={handleWorkflowChange}
                    />
                  )}

                  {/* 画布右上角 + 按钮（仅在有工作流时显示，唤起工具箱抽屉） */}
                  {workflow && (
                    <Button
                      size="icon"
                      className="absolute right-3 top-3 z-10 h-8 w-8"
                      onClick={() => setToolPaletteOpen(true)}
                      aria-label="添加节点"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  )}
                </div>

                {/* RunPanel 底部折叠条（默认 48px 显示运行按钮+状态，展开 240px 显示日志） */}
                {workflow && (
                  <motion.div
                    initial={false}
                    animate={{ height: runPanelExpanded ? 240 : 56 }}
                    transition={{ duration: 0.2, ease: 'easeInOut' }}
                    className="relative mt-2 shrink-0 overflow-hidden rounded-lg border border-border bg-card/40 backdrop-blur-sm"
                  >
                    <RunPanel
                      workflow={workflow}
                      runResult={runResult}
                      onRun={handleRun}
                      running={running}
                      logs={logs}
                      onFailure={onFailure}
                      onFailureChange={setOnFailure}
                      workflowId={currentWorkflowId || undefined}
                      streamingTokens={streamingTokens}
                    />
                    {/* 外层展开/收起按钮（绝对定位右上角，避免修改 RunPanel 内部） */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="absolute right-2 top-2 z-10 h-7 w-7"
                      onClick={() => setRunPanelExpanded((e) => !e)}
                      aria-expanded={runPanelExpanded}
                      aria-label={runPanelExpanded ? '收起日志' : '展开日志'}
                    >
                      {runPanelExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronUp className="h-4 w-4" />
                      )}
                    </Button>
                  </motion.div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>

      {/* 工具箱浮动按钮（右下角，T 键唤起抽屉）—— 仅桌面端显示，ghost variant 与主题一致 */}
      <Button
        variant="ghost"
        size="icon"
        className="fixed bottom-4 right-4 z-30 hidden h-12 w-12 rounded-full border border-border bg-background/80 backdrop-blur-xl hover:bg-accent md:inline-flex"
        onClick={() => setToolPaletteOpen(true)}
        aria-label="打开工具箱"
      >
        <Wrench className="h-5 w-5" />
      </Button>

      {/* 工具箱浮动抽屉（side=right，320px 宽） */}
      <Sheet open={toolPaletteOpen} onOpenChange={setToolPaletteOpen}>
        <SheetContent side="right" className="flex w-full max-w-[90vw] flex-col sm:w-[320px]">
          <SheetHeader className="shrink-0">
            <SheetTitle>工具箱</SheetTitle>
          </SheetHeader>
          <div className="mt-2 min-h-0 flex-1 overflow-hidden">
            <ToolPalette />
          </div>
        </SheetContent>
      </Sheet>

      {/* 节点配置抽屉：选中节点时右侧滑出（selectedNodeId 控制，宽 360px） */}
      <Sheet
        open={!!selectedNodeId}
        onOpenChange={(o) => {
          if (!o) setSelectedNodeId(null)
        }}
      >
        <SheetContent side="right" className="flex w-full max-w-[90vw] flex-col sm:w-[360px]">
          <SheetHeader className="shrink-0">
            <SheetTitle>节点详情</SheetTitle>
          </SheetHeader>
          <div className="mt-2 min-h-0 flex-1 overflow-hidden">
            <NodeInspector
              step={selectedStep}
              steps={workflow?.steps || []}
              edges={workflow?.edges || []}
              onParamsChange={handleParamsChange}
            />
          </div>
        </SheetContent>
      </Sheet>

      {/* 工作流列表浮层（sidebar 'workflows' 触发） */}
      <Dialog open={showWorkflowList} onOpenChange={setShowWorkflowList}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>工作流</DialogTitle>
            <DialogDescription>查看、加载与管理已保存的工作流</DialogDescription>
          </DialogHeader>
          <WorkflowList
            ref={workflowListRef}
            currentWorkflowId={currentWorkflowId}
            onLoad={(id) => {
              handleLoadWorkflow(id)
              setShowWorkflowList(false)
            }}
            onRefresh={handleListRefresh}
          />
        </DialogContent>
      </Dialog>

      {/* 保存工作流浮层 */}
      <Dialog open={showSaveDialog} onOpenChange={setShowSaveDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>保存工作流</DialogTitle>
            <DialogDescription>输入工作流名称以保存当前工作流</DialogDescription>
          </DialogHeader>
          <Input
            type="text"
            placeholder="请输入工作流名称"
            value={workflowName}
            onChange={(e) => setWorkflowName(e.target.value)}
            autoFocus
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSave()
            }}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowSaveDialog(false)} disabled={saving}>
              取消
            </Button>
            <Button onClick={handleSave} disabled={saving || !workflowName.trim()}>
              {saving ? '保存中...' : '确认保存'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 澄清补充浮层：后端返回 need_clarification 时弹出，复用现有 clarificationQuestions 状态与 handleClarificationSubmit 回调 */}
      <Dialog
        open={clarificationQuestions.length > 0}
        onOpenChange={(o) => {
          if (!o) {
            setClarificationQuestions([])
            setPendingRequirement('')
            setClarifyAnswer('')
          }
        }}
      >
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>需要更多信息</DialogTitle>
            <DialogDescription>请补充以下信息，以便生成更精准的工作流</DialogDescription>
          </DialogHeader>
          <ul className="flex flex-col gap-2 text-sm">
            {clarificationQuestions.map((q, i) => (
              <li key={i} className="flex items-start gap-2">
                <HelpCircle className="h-4 w-4 shrink-0 text-primary" aria-hidden />
                <span>{q}</span>
              </li>
            ))}
          </ul>
          <Textarea
            placeholder="请补充以上信息..."
            value={clarifyAnswer}
            onChange={(e) => setClarifyAnswer(e.target.value)}
            rows={4}
            disabled={loading}
          />
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setClarificationQuestions([])
                setPendingRequirement('')
                setClarifyAnswer('')
              }}
              disabled={loading}
            >
              取消
            </Button>
            <Button
              onClick={() => {
                if (clarifyAnswer.trim()) {
                  handleClarificationSubmit(clarifyAnswer.trim())
                  setClarifyAnswer('')
                }
              }}
              disabled={loading || !clarifyAnswer.trim()}
            >
              {loading ? '生成中...' : '补充并重新生成'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 执行历史浮层（Sheet 从右侧滑入） */}
      <Sheet open={showRunHistory && !!currentWorkflowId} onOpenChange={setShowRunHistory}>
        <SheetContent side="right" className="flex w-full max-w-[90vw] flex-col sm:w-[520px]">
          <SheetHeader>
            <SheetTitle>执行历史</SheetTitle>
          </SheetHeader>
          {currentWorkflowId && (
            <Suspense fallback={null}>
              <RunHistory
                workflowId={currentWorkflowId}
                onClose={() => setShowRunHistory(false)}
                onSelectRun={() => {
                  // 重试后新 run 详情已在历史面板内自动展开展示
                  // 此回调预留供父组件扩展（如主视图加载该 run）
                }}
              />
            </Suspense>
          )}
        </SheetContent>
      </Sheet>

      {/* 凭证配置浮层 */}
      <Dialog open={showCredentials} onOpenChange={setShowCredentials}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>凭证管理</DialogTitle>
            <DialogDescription>管理各工具的 API 凭证</DialogDescription>
          </DialogHeader>
          <Suspense fallback={null}>
            <CredentialPanel onClose={() => setShowCredentials(false)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* 偏好设置浮层 */}
      <Dialog open={showPreferences} onOpenChange={setShowPreferences}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>偏好设置</DialogTitle>
            <DialogDescription>管理用户偏好,执行期自动填充工具参数</DialogDescription>
          </DialogHeader>
          <Suspense fallback={null}>
            <PreferencePanel onClose={() => setShowPreferences(false)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* 定时任务浮层 */}
      <Dialog open={showSchedule} onOpenChange={setShowSchedule}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>定时任务</DialogTitle>
            <DialogDescription>查看与管理已配置的定时调度任务</DialogDescription>
          </DialogHeader>
          <Suspense fallback={null}>
            <SchedulePanel onClose={() => setShowSchedule(false)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* 执行统计 Dashboard 浮层（较宽） */}
      <Dialog open={showDashboard} onOpenChange={setShowDashboard}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>执行统计</DialogTitle>
            <DialogDescription>查看工作流执行的统计数据与趋势</DialogDescription>
          </DialogHeader>
          <Suspense fallback={null}>
            <DashboardPanel onClose={() => setShowDashboard(false)} />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* 导出工作流浮层（sidebar 'export' 触发） */}
      <Dialog open={showExport} onOpenChange={setShowExport}>
        <DialogContent className="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>导出工作流</DialogTitle>
            <DialogDescription>导出当前工作流为 JSON / Markdown</DialogDescription>
          </DialogHeader>
          <Suspense fallback={null}>
            <ExportPanel workflow={workflow} />
          </Suspense>
        </DialogContent>
      </Dialog>

      {/* ⌘K 命令面板 */}
      <Command
        open={commandOpen}
        onOpenChange={setCommandOpen}
        workflows={workflows}
        onLoadWorkflow={handleLoadWorkflow}
        onNewWorkflow={() => {
          handleNewWorkflow()
          setCommandOpen(false)
        }}
        onToggleTheme={handleThemeToggle}
        onNavigate={(p) => {
          // Command 的 'dashboard' 实际指执行统计浮层（Sidebar 已重命名为 'dashboard-stats'）
          handlePanelChange(p === 'dashboard' ? 'dashboard-stats' : (p as SidebarPanel))
          setCommandOpen(false)
        }}
      />

      {/* 未保存修改保护：新建 / 使用模板前确认丢弃未保存更改 */}
      <ConfirmDialog
        open={pendingAction !== null}
        title="丢弃未保存的修改？"
        message="当前工作流有未保存的修改，继续将丢失这些更改。"
        confirmText="丢弃并继续"
        danger
        onConfirm={() => {
          if (pendingAction === 'new') doNewWorkflow()
          else if (pendingAction === 'template') doUseTemplate(pendingTemplateReq)
          setPendingAction(null)
          setPendingTemplateReq('')
          setHasUnsavedChanges(false)
        }}
        onCancel={() => {
          setPendingAction(null)
          setPendingTemplateReq('')
        }}
      />

      {/* ===== 移动端底部 tab bar（<768px 显示，5 个图标按钮） ===== */}
      <nav className="fixed bottom-0 left-0 right-0 z-30 flex h-14 items-stretch border-t border-border bg-background/80 backdrop-blur-xl md:hidden">
        {/* 视图切换：Dashboard / Editor / Templates */}
        <button
          type="button"
          onClick={() => setCurrentView('dashboard')}
          aria-label="仪表盘视图"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            currentView === 'dashboard' ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {currentView === 'dashboard' && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <LayoutGrid className="h-5 w-5" />
          <span>仪表盘</span>
        </button>

        <button
          type="button"
          onClick={() => setCurrentView('editor')}
          aria-label="编辑器视图"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            currentView === 'editor' ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {currentView === 'editor' && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <Workflow className="h-5 w-5" />
          <span>编辑器</span>
        </button>

        <button
          type="button"
          onClick={() => setCurrentView('templates')}
          aria-label="模板视图"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            currentView === 'templates' ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {currentView === 'templates' && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <Grid3x3 className="h-5 w-5" />
          <span>模板</span>
        </button>

        {/* 工作流列表 */}
        <button
          type="button"
          onClick={() => {
            setMobileInspectorOpen(false)
            setToolPaletteOpen(false)
            handlePanelChange('workflows')
          }}
          aria-label="工作流列表"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            showWorkflowList ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {showWorkflowList && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <Workflow className="h-5 w-5" />
          <span>工作流</span>
        </button>

        {/* 工具箱 */}
        <button
          type="button"
          onClick={() => {
            setMobileInspectorOpen(false)
            setToolPaletteOpen((o) => !o)
          }}
          aria-label="工具箱"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            toolPaletteOpen ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {toolPaletteOpen && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <Wrench className="h-5 w-5" />
          <span>工具箱</span>
        </button>

        {/* 节点检查器 */}
        <button
          type="button"
          onClick={() => {
            setToolPaletteOpen(false)
            setMobileInspectorOpen((o) => !o)
          }}
          aria-label="节点检查器"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            mobileInspectorOpen ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {mobileInspectorOpen && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <Info className="h-5 w-5" />
          <span>检查器</span>
        </button>

        {/* 执行历史 */}
        <button
          type="button"
          onClick={() => {
            setMobileInspectorOpen(false)
            setToolPaletteOpen(false)
            handlePanelChange('history')
          }}
          aria-label="执行历史"
          className={cn(
            'relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium transition-colors',
            showRunHistory && !!currentWorkflowId ? 'text-primary' : 'text-muted-foreground'
          )}
        >
          {showRunHistory && !!currentWorkflowId && (
            <span className="absolute top-0 h-0.5 w-8 rounded-full bg-primary" />
          )}
          <History className="h-5 w-5" />
          <span>历史</span>
        </button>

        {/* 主题切换 */}
        <button
          type="button"
          onClick={handleThemeToggle}
          aria-label="切换主题"
          className="relative flex flex-1 flex-col items-center justify-center gap-0.5 text-[10px] font-medium text-muted-foreground transition-colors hover:text-foreground"
        >
          {theme === 'dark' ? (
            <Sun className="h-5 w-5" />
          ) : (
            <Moon className="h-5 w-5" />
          )}
          <span>主题</span>
        </button>
      </nav>

      {/* 移动端 inspector 底部 Sheet（side=bottom，宽满屏，高 60vh；展示选中节点详情） */}
      <Sheet open={mobileInspectorOpen} onOpenChange={setMobileInspectorOpen}>
        <SheetContent side="bottom" className="h-[60vh] gap-0 p-0">
          <div className="flex h-12 shrink-0 items-center border-b border-border px-4">
            <SheetTitle className="text-base font-semibold">检查器</SheetTitle>
          </div>
          <div className="h-[calc(60vh-3rem)] overflow-hidden">
            <NodeInspector
              step={selectedStep}
              steps={workflow?.steps || []}
              edges={workflow?.edges || []}
              onParamsChange={handleParamsChange}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  )
}

// App 外层包裹 ToastProvider，提供全局 Toast 通知能力
function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  )
}

export default App
