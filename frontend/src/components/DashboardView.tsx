// Dashboard 概览视图 - 登录后落地页，聚合工作流列表 + 执行统计 + 模板推荐
import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Plus,
  LayoutGrid,
  Sparkles,
  TrendingUp,
  CheckCircle2,
  Clock,
  Zap,
  ArrowRight,
  Inbox,
  Webhook,
  Hand,
  Coins,
} from 'lucide-react'
import { listWorkflows, getDashboardStats, type DashboardStats } from '../services/api'
import { SCENARIO_TEMPLATES } from './ScenarioTemplates'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Skeleton } from '@/components/ui/Skeleton'

interface WorkflowItem {
  id: string
  name: string
  scenario: string
  schedule_enabled: boolean
  webhook_id: string | null
  triggers: string[]
  created_at: string
  updated_at: string
}

interface DashboardViewProps {
  onOpenWorkflow: (id: string) => void
  onNewWorkflow: () => void
  onBrowseTemplates: () => void
  onUseTemplate: (requirement: string) => void
}

// 相对时间格式化：用 Intl.RelativeTimeFormat 输出中文相对时间（如 "2 小时前"）
function formatRelativeTime(dateStr: string): string {
  if (!dateStr) return ''
  const then = new Date(dateStr).getTime()
  if (Number.isNaN(then)) return dateStr
  const diffMs = Date.now() - then
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMin / 60)
  const diffDay = Math.floor(diffHour / 24)
  const rtf = new Intl.RelativeTimeFormat('zh', { numeric: 'auto' })
  if (diffDay >= 1) return rtf.format(-diffDay, 'day')
  if (diffHour >= 1) return rtf.format(-diffHour, 'hour')
  if (diffMin >= 1) return rtf.format(-diffMin, 'minute')
  return '刚刚'
}

// 平均耗时格式化：<1s 显示 ms，否则保留 1 位小数秒（1234ms → "1.2s"）
function formatAvgTime(ms: number): string {
  if (!ms || ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// B4: Token 数量格式化：<1000 原样,>=1000 用 k 单位(1234 → "1.2k")
function formatTokenCount(n: number): string {
  if (!n || n < 1000) return `${n}`
  return `${(n / 1000).toFixed(1)}k`
}

// 构建 SVG sparkline polyline 点串（0 基线 → max，紫色 stroke 用）
function buildSparkline(values: number[], width = 120, height = 28): string {
  if (values.length === 0) return ''
  const max = Math.max(...values, 1)
  const stepX = values.length > 1 ? width / (values.length - 1) : width
  return values
    .map((v, i) => {
      const x = i * stepX
      const y = height - (v / max) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

// 触发类型判断：schedule 优先于 webhook，否则手动
function getTriggerBadge(triggers: string[]): { label: string; icon: typeof Clock } {
  if (triggers?.includes('schedule_trigger')) return { label: '定时', icon: Clock }
  if (triggers?.includes('webhook_trigger')) return { label: 'Webhook', icon: Webhook }
  return { label: '手动', icon: Hand }
}

export function DashboardView({
  onOpenWorkflow,
  onNewWorkflow,
  onBrowseTemplates,
  onUseTemplate,
}: DashboardViewProps) {
  const [workflows, setWorkflows] = useState<WorkflowItem[]>([])
  const [workflowsLoading, setWorkflowsLoading] = useState(true)
  const [workflowsError, setWorkflowsError] = useState('')

  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [statsLoading, setStatsLoading] = useState(true)
  const [statsError, setStatsError] = useState('')

  // 并行加载工作流列表 + 统计数据
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setWorkflowsLoading(true)
      setWorkflowsError('')
      try {
        const list = await listWorkflows()
        if (!cancelled) setWorkflows(list)
      } catch (e) {
        if (!cancelled) setWorkflowsError(e instanceof Error ? e.message : '加载工作流失败')
      } finally {
        if (!cancelled) setWorkflowsLoading(false)
      }
    })()
    ;(async () => {
      setStatsLoading(true)
      setStatsError('')
      try {
        const data = await getDashboardStats()
        if (!cancelled) setStats(data)
      } catch (e) {
        if (!cancelled) setStatsError(e instanceof Error ? e.message : '加载统计数据失败')
      } finally {
        if (!cancelled) setStatsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  // 工作流按 updated_at 降序取前 6
  const recentWorkflows = useMemo(() => {
    return [...workflows]
      .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
      .slice(0, 6)
  }, [workflows])

  const hasWorkflows = workflows.length > 0
  // 防御性判空:stats.trend 可能在某些边缘情况下为 undefined(如后端返回不完整)
  const weekTotal = stats && Array.isArray(stats.trend) ? stats.trend.reduce((sum, t) => sum + (t?.total || 0), 0) : 0
  const popularTemplates = SCENARIO_TEMPLATES.slice(0, 4)

  return (
    <div className="overflow-y-auto h-full p-6 pb-20 md:p-8 md:pb-8">
      <div className="mx-auto flex max-w-6xl flex-col gap-8">
        {/* 顶部欢迎区 */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-2">
            <h1 className="text-4xl font-bold tracking-tight">FlowGenie</h1>
            <p className="text-muted-foreground">AI 工作流编排，一句话启动</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Button onClick={onNewWorkflow}>
              <Plus size={16} className="mr-2" />
              新建空白工作流
            </Button>
            <Button variant="outline" onClick={onBrowseTemplates}>
              <LayoutGrid size={16} className="mr-2" />
              浏览模板
            </Button>
            <Button variant="outline" onClick={onNewWorkflow}>
              <Sparkles size={16} className="mr-2" />
              AI 生成
            </Button>
          </div>
        </motion.div>

        {/* 空状态引导提示（无工作流时显示在欢迎区与模板之间） */}
        {!workflowsLoading && !hasWorkflows && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, type: 'spring', stiffness: 300, damping: 30 }}
          >
            <Card className="border-dashed">
              <CardContent className="flex flex-col items-center justify-center gap-2 py-8 text-center">
                <Inbox size={28} className="text-muted-foreground" />
                <p className="text-sm text-muted-foreground">
                  还没有工作流，从一个模板开始吧
                </p>
                <Button variant="outline" size="sm" onClick={onBrowseTemplates} className="mt-1">
                  浏览全部模板
                  <ArrowRight size={14} className="ml-2" />
                </Button>
              </CardContent>
            </Card>
          </motion.div>
        )}

        {/* KPI 卡片网格（仅有工作流时显示） */}
        {hasWorkflows && (
          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">执行概览</h2>
            {statsLoading ? (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Card key={i} className="p-5">
                    <Skeleton className="mb-3 h-3 w-20" />
                    <Skeleton className="h-8 w-3/5" />
                  </Card>
                ))}
              </div>
            ) : statsError ? (
              <p className="text-sm text-destructive">{statsError}</p>
            ) : stats ? (
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {/* 总执行数 - 紫色强调 */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0, type: 'spring', stiffness: 300, damping: 30 }}
                >
                  <Card className="h-full">
                    <CardContent className="flex flex-col gap-2 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">总执行数</span>
                        <TrendingUp size={16} className="text-primary" />
                      </div>
                      <div className="text-3xl font-bold text-primary">{stats.total_runs}</div>
                    </CardContent>
                  </Card>
                </motion.div>
                {/* 成功率 - 绿色强调 */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.05, type: 'spring', stiffness: 300, damping: 30 }}
                >
                  <Card className="h-full">
                    <CardContent className="flex flex-col gap-2 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">成功率</span>
                        <CheckCircle2 size={16} className="text-success" />
                      </div>
                      <div className="text-3xl font-bold text-success">{stats.success_rate}%</div>
                    </CardContent>
                  </Card>
                </motion.div>
                {/* 平均耗时 - 蓝色强调 */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1, type: 'spring', stiffness: 300, damping: 30 }}
                >
                  <Card className="h-full">
                    <CardContent className="flex flex-col gap-2 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">平均耗时</span>
                        <Clock size={16} className="text-info" />
                      </div>
                      <div className="text-3xl font-bold text-info">
                        {formatAvgTime(stats.avg_time_ms)}
                      </div>
                    </CardContent>
                  </Card>
                </motion.div>
                {/* 本周执行数 - 橙色强调 + sparkline 迷你趋势图 */}
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.15, type: 'spring', stiffness: 300, damping: 30 }}
                >
                  <Card className="h-full">
                    <CardContent className="flex flex-col gap-2 p-5">
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-muted-foreground">本周执行数</span>
                        <Zap size={16} className="text-warning" />
                      </div>
                      <div className="text-3xl font-bold text-warning">{weekTotal}</div>
                      {stats?.trend && stats.trend.length > 0 && (
                        <svg
                          viewBox="0 0 120 28"
                          preserveAspectRatio="none"
                          className="mt-1 h-7 w-full"
                          aria-label="近 7 天执行趋势"
                        >
                          <polyline
                            fill="none"
                            stroke="hsl(var(--primary))"
                            strokeWidth="1.5"
                            strokeLinejoin="round"
                            strokeLinecap="round"
                            points={buildSparkline(stats.trend.map((t) => t?.total || 0))}
                          />
                        </svg>
                      )}
                    </CardContent>
                  </Card>
                </motion.div>
              </div>
            ) : null}
          </section>
        )}

        {/* B4: LLM Token 用量概览(仅有工作流且有 token 用量时显示) */}
        {hasWorkflows && !statsLoading && !statsError && stats && stats.token_stats && stats.token_stats.total_tokens > 0 && (
          <motion.section
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 300, damping: 30 }}
            className="flex flex-col gap-3"
          >
            <h2 className="text-lg font-semibold">LLM Token 用量</h2>
            <Card>
              <CardContent className="flex flex-col gap-4 p-5">
                {/* 顶部:总用量 + 调用次数 + 输入/输出拆分 */}
                <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                  <div className="flex flex-col gap-1">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Coins size={14} className="text-primary" /> 总 Token
                    </span>
                    <span className="text-2xl font-bold text-primary">
                      {formatTokenCount(stats.token_stats.total_tokens)}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground">输入 Token</span>
                    <span className="text-2xl font-bold">
                      {formatTokenCount(stats.token_stats.prompt_tokens)}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground">输出 Token</span>
                    <span className="text-2xl font-bold">
                      {formatTokenCount(stats.token_stats.completion_tokens)}
                    </span>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted-foreground">调用次数</span>
                    <span className="text-2xl font-bold">{stats.token_stats.calls}</span>
                  </div>
                </div>
                {/* 底部:按模型分布(仅有 by_model 数据时显示) */}
                {Object.keys(stats.token_stats.by_model).length > 0 && (
                  <div className="flex flex-wrap gap-2 border-t border-border pt-3">
                    {Object.entries(stats.token_stats.by_model)
                      .sort(([, a], [, b]) => b.total_tokens - a.total_tokens)
                      .map(([model, info]) => (
                        <div
                          key={model}
                          className="flex items-center gap-2 rounded-md border border-border bg-card/40 px-3 py-1.5 text-xs"
                          title={`${model}: ${info.total_tokens} tokens / ${info.calls} 次`}
                        >
                          <span className="font-medium">{model}</span>
                          <span className="text-muted-foreground">
                            {formatTokenCount(info.total_tokens)}
                          </span>
                          <span className="text-muted-foreground/70">· {info.calls} 次</span>
                        </div>
                      ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </motion.section>
        )}

        {/* 我的工作流卡片网格（仅有工作流时显示） */}
        {hasWorkflows && (
          <section className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">我的工作流</h2>
            </div>
            {workflowsLoading ? (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
                  <Card key={i} className="p-5">
                    <Skeleton className="mb-3 h-4 w-2/3" />
                    <Skeleton className="mb-4 h-3 w-full" />
                    <div className="flex justify-between">
                      <Skeleton className="h-5 w-14 rounded-full" />
                      <Skeleton className="h-8 w-16" />
                    </div>
                  </Card>
                ))}
              </div>
            ) : workflowsError ? (
              <p className="text-sm text-destructive">{workflowsError}</p>
            ) : (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {recentWorkflows.map((wf, index) => {
                  const badge = getTriggerBadge(wf.triggers)
                  const TriggerIcon = badge.icon
                  return (
                    <motion.div
                      key={wf.id}
                      initial={{ opacity: 0, y: 20 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: index * 0.05, type: 'spring', stiffness: 300, damping: 30 }}
                      whileHover={{ scale: 1.02 }}
                    >
                      <Card className="h-full transition-colors hover:border-primary/50">
                        <CardHeader className="pb-2">
                          <CardTitle className="truncate text-base font-semibold" title={wf.name}>
                            {wf.name}
                          </CardTitle>
                          <CardDescription className="truncate text-xs" title={wf.scenario}>
                            {wf.scenario}
                          </CardDescription>
                        </CardHeader>
                        <CardContent className="flex flex-col gap-3">
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary" className="gap-1">
                              <TriggerIcon size={12} />
                              {badge.label}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {formatRelativeTime(wf.updated_at)}
                            </span>
                          </div>
                        </CardContent>
                        <CardFooter className="justify-end p-6 pt-0">
                          <Button size="sm" variant="ghost" onClick={() => onOpenWorkflow(wf.id)}>
                            打开
                            <ArrowRight size={14} className="ml-2" />
                          </Button>
                        </CardFooter>
                      </Card>
                    </motion.div>
                  )
                })}
              </div>
            )}
          </section>
        )}

        {/* 热门模板推荐（始终显示） */}
        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">热门模板</h2>
            <Button variant="link" className="h-auto p-0 text-sm" onClick={onBrowseTemplates}>
              浏览全部
              <ArrowRight size={14} className="ml-1" />
            </Button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
            {popularTemplates.map((tpl, index) => (
              <motion.div
                key={tpl.key}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05, type: 'spring', stiffness: 300, damping: 30 }}
                whileHover={{ scale: 1.02 }}
              >
                <Card className="flex h-full flex-col transition-colors hover:border-primary/50">
                  <CardHeader className="pb-2">
                    <tpl.icon className="h-8 w-8 text-primary" />
                    <CardTitle className="text-sm font-semibold">{tpl.title}</CardTitle>
                  </CardHeader>
                  <CardContent className="flex-1">
                    <p className="line-clamp-2 text-xs text-muted-foreground">{tpl.description}</p>
                  </CardContent>
                  <CardFooter className="justify-end p-6 pt-0">
                    <Button size="sm" variant="ghost" onClick={() => onUseTemplate(tpl.requirement)}>
                      使用
                      <ArrowRight size={14} className="ml-2" />
                    </Button>
                  </CardFooter>
                </Card>
              </motion.div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
