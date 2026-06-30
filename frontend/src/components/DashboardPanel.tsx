// 执行统计 Dashboard 面板 - 展示聚合统计、7 天趋势与工具使用频率
import { useState, useEffect, useCallback } from 'react'
import type { CSSProperties } from 'react'
import { motion } from 'framer-motion'
import { ChartColumn, RefreshCw, Loader, X, TriangleAlert, Trophy, AlertCircle, Gauge, ChevronDown, ChevronRight, Coins, Download } from 'lucide-react'
import { getDashboardStats, exportDashboardReport, type DashboardStats } from '../services/api'
import {
  Skeleton,
  SkeletonNumber,
  SkeletonTrendChart,
  SkeletonToolBar,
} from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { Button } from '@/components/ui/Button'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from '@/components/ui/Card'
import { Alert, AlertDescription } from '@/components/ui/Alert'
import { cn } from '@/lib/utils'

interface Props {
  onClose: () => void
}

export function DashboardPanel({ onClose }: Props) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // 趋势柱状图 hover 的柱子索引（用于显示 tooltip）
  const [hoveredTrendIndex, setHoveredTrendIndex] = useState<number | null>(null)
  // 趋势天数切换(7/30/90)
  const [days, setDays] = useState(7)
  // 失败聚类展开状态(按聚类名维度)
  const [expandedCluster, setExpandedCluster] = useState<string | null>(null)
  // D2: 报表导出 loading 状态
  const [exporting, setExporting] = useState(false)

  const refresh = useCallback(async (selectedDays: number = days) => {
    setLoading(true)
    setError('')
    try {
      const data = await getDashboardStats(selectedDays)
      setStats(data)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载统计数据失败')
    } finally {
      setLoading(false)
    }
  }, [days])

  // D2: 导出 Dashboard 统计报表为 Excel(多 sheet)
  const handleExportReport = async () => {
    if (exporting) return
    setExporting(true)
    setError('')
    try {
      await exportDashboardReport(days)
    } catch (e) {
      setError(e instanceof Error ? e.message : '导出报表失败')
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [refresh])

  // 切换天数时重新请求
  const handleDaysChange = (newDays: number) => {
    setDays(newDays)
    refresh(newDays)
  }

  // 趋势柱状图最大值（用于计算高度比例）
  const trendMax = stats
    ? Math.max(...stats.trend.map((t) => t.total), 1)
    : 1
  // 工具使用最大值（用于计算宽度比例）
  const toolMax = stats && stats.tool_usage.length > 0
    ? Math.max(...stats.tool_usage.map((t) => t.count), 1)
    : 1

  const formatTime = (ms: number) => {
    if (ms < 1000) return `${ms}ms`
    return `${(ms / 1000).toFixed(1)}s`
  }

  // B4: Token 数量格式化(<1000 原样,>=1000 用 k 单位)
  const formatTokenCount = (n: number) => {
    if (!n || n < 1000) return `${n}`
    return `${(n / 1000).toFixed(1)}k`
  }

  const formatDate = (dateStr: string) => {
    // 取 MM-DD
    const parts = dateStr.split('-')
    if (parts.length >= 3) return `${parts[1]}-${parts[2]}`
    return dateStr
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部工具条：刷新 / 关闭 */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-lg font-semibold">
          <ChartColumn size={18} /> 执行统计 Dashboard
        </h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-8 gap-1"
            onClick={handleExportReport}
            disabled={exporting || loading || !stats || stats.total_runs === 0}
            title="导出统计报表为 Excel(多 sheet)"
          >
            <Download size={14} className={cn(exporting && 'animate-pulse')} />
            {exporting ? '导出中...' : '导出报表'}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => refresh()}
            disabled={loading}
            title="刷新"
            aria-label="刷新统计数据"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title="关闭"
            aria-label="关闭统计面板"
          >
            <X size={16} />
          </Button>
        </div>
      </div>

      {loading ? (
        // 加载态：统计数字 + 趋势图 + 工具条均用骨架占位
        <>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="p-4">
                <Skeleton className="mb-2 h-3 w-20" />
                <SkeletonNumber />
              </Card>
            ))}
          </div>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">最近 {days} 天执行趋势</CardTitle>
            </CardHeader>
            <CardContent>
              <SkeletonTrendChart />
              <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-success" /> 成功
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-destructive" /> 失败
                </span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">工具使用频率 Top 5</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-2">
                {Array.from({ length: 5 }).map((_, i) => (
                  <SkeletonToolBar key={i} />
                ))}
              </div>
            </CardContent>
          </Card>
        </>
      ) : error ? (
        <Alert variant="destructive">
          <TriangleAlert size={16} />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : !stats || stats.total_runs === 0 ? (
        <EmptyState
          icon={<ChartColumn size={24} />}
          title="暂无执行数据"
          description="执行工作流后将在此查看统计"
        />
      ) : (
        <>
          {/* 顶部 4 个统计卡片 */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  总执行数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold">{stats.total_runs}</div>
              </CardContent>
            </Card>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.05, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  成功率
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-success">
                  {stats.success_rate}%
                </div>
              </CardContent>
            </Card>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  平均耗时
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-primary">
                  {formatTime(stats.avg_time_ms)}
                </div>
              </CardContent>
            </Card>
            </motion.div>
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-xs font-medium text-muted-foreground">
                  失败数
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-bold text-destructive">
                  {stats.failed_count}
                </div>
              </CardContent>
            </Card>
            </motion.div>
          </div>

          {/* 中部：执行趋势（柱状图,可切换 7/30/90 天） */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 300, damping: 30 }}
          >
          <Card>
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm">最近 {days} 天执行趋势</CardTitle>
                <div className="flex items-center gap-1">
                  {[7, 30, 90].map((d) => (
                    <Button
                      key={d}
                      variant={days === d ? 'default' : 'outline'}
                      size="sm"
                      className="h-6 px-2 text-xs"
                      onClick={() => handleDaysChange(d)}
                      disabled={loading}
                    >
                      {d}天
                    </Button>
                  ))}
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="dashboard-trend-chart flex items-end gap-1 h-[120px] py-3">
                {stats.trend.map((t, index) => {
                  const totalHeight = (t.total / trendMax) * 100
                  const successHeight = t.total > 0 ? (t.success / t.total) * 100 : 0
                  const isHovered = hoveredTrendIndex === index
                  return (
                    <div
                      key={t.date}
                      className="dashboard-trend-bar-wrap relative flex flex-1 min-w-0 flex-col items-center justify-end h-full"
                      onMouseEnter={() => setHoveredTrendIndex(index)}
                      onMouseLeave={() => setHoveredTrendIndex(null)}
                    >
                      {/* hover tooltip：日期 + 执行数 + 成功/失败数 */}
                      {isHovered && (
                        <div className="dashboard-trend-tooltip absolute bottom-full left-1/2 z-10 mb-2 -translate-x-1/2 whitespace-nowrap rounded-md border bg-popover p-2 text-xs shadow-md">
                          <div className="font-medium">{t.date}</div>
                          <div className="flex justify-between gap-3">
                            <span>总计</span>
                            <span>{t.total}</span>
                          </div>
                          <div className="flex justify-between gap-3">
                            <span>成功</span>
                            <span className="font-semibold text-success">
                              {t.success}
                            </span>
                          </div>
                          <div className="flex justify-between gap-3">
                            <span>失败</span>
                            <span className="font-semibold text-destructive">
                              {t.failed}
                            </span>
                          </div>
                        </div>
                      )}
                      <div
                        className="dashboard-trend-bar-container dashboard-bar flex w-[70%] max-w-[36px] min-h-[4px] flex-col justify-end overflow-hidden rounded-t-sm mt-auto"
                        style={{
                          height: `${Math.max(totalHeight, 2)}%`,
                          background: t.total === 0 ? 'hsl(var(--border))' : undefined,
                          animationDelay: `${index * 50}ms`,
                        }}
                      >
                        {t.total > 0 && (
                          <>
                            <div
                              className="dashboard-trend-bar-success w-full"
                              style={{ height: `${successHeight}%` }}
                            />
                            <div
                              className="dashboard-trend-bar-failed w-full"
                              style={{ height: `${100 - successHeight}%` }}
                            />
                          </>
                        )}
                      </div>
                      <div className="mt-1 text-xs text-muted-foreground">
                        {formatDate(t.date)}
                      </div>
                      <div className="text-xs font-medium">{t.total}</div>
                    </div>
                  )
                })}
              </div>
              <div className="mt-2 flex gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-success" /> 成功
                </span>
                <span className="flex items-center gap-1">
                  <span className="inline-block h-2 w-2 rounded-full bg-destructive" /> 失败
                </span>
              </div>
            </CardContent>
          </Card>
          </motion.div>

          {/* 底部：工具使用频率 Top 5（横向条形图） */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, type: 'spring', stiffness: 300, damping: 30 }}
          >
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">工具使用频率 Top 5</CardTitle>
            </CardHeader>
            <CardContent>
              {stats.tool_usage.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无工具使用数据</p>
              ) : (
                <div className="flex flex-col gap-2">
                  {stats.tool_usage.map((t, index) => {
                    const width = (t.count / toolMax) * 100
                    return (
                      <div
                        key={t.tool}
                        className="grid grid-cols-[80px_1fr_30px] items-center gap-3"
                      >
                        <div className="truncate text-xs" title={t.tool}>
                          {t.tool}
                        </div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div
                            className="dashboard-tool-bar dashboard-tool-bar-fill h-full rounded-full"
                            style={
                              {
                                '--target-width': `${Math.max(width, 2)}%`,
                                background:
                                  'linear-gradient(90deg, hsl(var(--primary)), hsl(var(--primary) / 0.5))',
                                animationDelay: `${index * 50}ms`,
                              } as CSSProperties
                            }
                          />
                        </div>
                        <div className="text-right text-xs font-medium">{t.count}</div>
                      </div>
                    )
                  })}
                </div>
              )}
            </CardContent>
          </Card>
          </motion.div>

          {/* B4: LLM Token 用量统计(仅有 token 用量时显示) */}
          {stats.token_stats && stats.token_stats.total_tokens > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.22, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Coins size={16} /> LLM Token 用量
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <div className="rounded-md border border-border bg-card/40 p-2 text-center">
                    <div className="text-xs text-muted-foreground">总 Token</div>
                    <div className="text-lg font-bold text-primary">
                      {formatTokenCount(stats.token_stats.total_tokens)}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-card/40 p-2 text-center">
                    <div className="text-xs text-muted-foreground">输入</div>
                    <div className="text-lg font-bold">
                      {formatTokenCount(stats.token_stats.prompt_tokens)}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-card/40 p-2 text-center">
                    <div className="text-xs text-muted-foreground">输出</div>
                    <div className="text-lg font-bold">
                      {formatTokenCount(stats.token_stats.completion_tokens)}
                    </div>
                  </div>
                  <div className="rounded-md border border-border bg-card/40 p-2 text-center">
                    <div className="text-xs text-muted-foreground">调用次数</div>
                    <div className="text-lg font-bold">{stats.token_stats.calls}</div>
                  </div>
                </div>
                {Object.keys(stats.token_stats.by_model).length > 0 && (
                  <div className="mt-3 flex flex-col gap-2 border-t border-border pt-3">
                    <div className="text-xs font-medium text-muted-foreground">按模型分布</div>
                    {Object.entries(stats.token_stats.by_model)
                      .sort(([, a], [, b]) => b.total_tokens - a.total_tokens)
                      .map(([model, info]) => {
                        const modelMax = Math.max(
                          ...Object.values(stats.token_stats.by_model).map((m) => m.total_tokens),
                          1
                        )
                        const width = (info.total_tokens / modelMax) * 100
                        return (
                          <div
                            key={model}
                            className="grid grid-cols-[100px_1fr_70px] items-center gap-2"
                          >
                            <div className="truncate text-xs" title={model}>{model}</div>
                            <div className="h-2 overflow-hidden rounded-full bg-muted">
                              <div
                                className="h-full rounded-full"
                                style={{
                                  width: `${Math.max(width, 2)}%`,
                                  background:
                                    'linear-gradient(90deg, hsl(var(--primary)), hsl(var(--primary) / 0.5))',
                                }}
                              />
                            </div>
                            <div className="text-right text-xs font-medium">
                              {formatTokenCount(info.total_tokens)}
                              <span className="text-muted-foreground/70"> · {info.calls}次</span>
                            </div>
                          </div>
                        )
                      })}
                  </div>
                )}
              </CardContent>
            </Card>
            </motion.div>
          )}

          {/* 耗时分位数(P50/P90/P95/Max) */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25, type: 'spring', stiffness: 300, damping: 30 }}
          >
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Gauge size={16} /> 耗时分位数
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-4 gap-2">
                {[
                  { label: 'P50', value: stats.duration_percentiles.p50, color: 'text-primary' },
                  { label: 'P90', value: stats.duration_percentiles.p90, color: 'text-warning' },
                  { label: 'P95', value: stats.duration_percentiles.p95, color: 'text-warning' },
                  { label: 'Max', value: stats.duration_percentiles.max, color: 'text-destructive' },
                ].map((p) => (
                  <div key={p.label} className="rounded-md border border-border bg-card/40 p-2 text-center">
                    <div className="text-xs text-muted-foreground">{p.label}</div>
                    <div className={cn('text-lg font-bold', p.color)}>{formatTime(p.value)}</div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
          </motion.div>

          {/* 工作流排名表(Top 10) */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, type: 'spring', stiffness: 300, damping: 30 }}
          >
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Trophy size={16} /> 工作流执行排名 Top 10
              </CardTitle>
            </CardHeader>
            <CardContent>
              {stats.workflow_ranking.length === 0 ? (
                <p className="text-sm text-muted-foreground">暂无工作流执行数据</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-border text-muted-foreground">
                        <th className="py-1.5 pr-2 text-left font-medium">#</th>
                        <th className="py-1.5 pr-2 text-left font-medium">名称</th>
                        <th className="py-1.5 pr-2 text-right font-medium">执行数</th>
                        <th className="py-1.5 pr-2 text-right font-medium">成功率</th>
                        <th className="py-1.5 text-right font-medium">平均耗时</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.workflow_ranking.map((w, i) => (
                        <tr key={w.workflow_id} className="border-b border-border/50 hover:bg-accent/30">
                          <td className="py-1.5 pr-2 text-muted-foreground">{i + 1}</td>
                          <td className="py-1.5 pr-2">
                            <span className="truncate" title={w.name}>{w.name}</span>
                          </td>
                          <td className="py-1.5 pr-2 text-right">{w.total}</td>
                          <td className="py-1.5 pr-2 text-right">
                            <span
                              className={cn(
                                'inline-block rounded px-1.5 py-0.5 text-xs font-medium',
                                w.success_rate >= 80
                                  ? 'bg-success/15 text-success'
                                  : w.success_rate >= 50
                                  ? 'bg-warning/15 text-warning'
                                  : 'bg-destructive/15 text-destructive'
                              )}
                            >
                              {w.success_rate}%
                            </span>
                          </td>
                          <td className="py-1.5 text-right text-muted-foreground">{formatTime(w.avg_time_ms)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
          </motion.div>

          {/* 失败原因聚类(Top 5) */}
          {stats.failure_clusters.length > 0 && (
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.35, type: 'spring', stiffness: 300, damping: 30 }}
            >
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm">
                  <AlertCircle size={16} /> 失败原因聚类 Top 5
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-col gap-2">
                  {stats.failure_clusters.map((c) => {
                    const isExpanded = expandedCluster === c.cluster
                    return (
                      <div key={c.cluster} className="rounded-md border border-border bg-card/40">
                        <button
                          type="button"
                          className="flex w-full items-center gap-2 p-2 text-left hover:bg-accent/30"
                          onClick={() => setExpandedCluster(isExpanded ? null : c.cluster)}
                        >
                          {isExpanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                          <span className="flex-1 truncate text-sm font-medium">{c.cluster}</span>
                          <span className="rounded bg-destructive/15 px-1.5 py-0.5 text-xs font-medium text-destructive">
                            {c.count} 次
                          </span>
                        </button>
                        {isExpanded && c.sample_error && (
                          <pre className="mx-2 mb-2 max-h-40 overflow-auto rounded bg-destructive/10 p-2 text-xs whitespace-pre-wrap break-all text-destructive">
                            {c.sample_error}
                          </pre>
                        )}
                      </div>
                    )
                  })}
                </div>
              </CardContent>
            </Card>
            </motion.div>
          )}
        </>
      )}
    </div>
  )
}
