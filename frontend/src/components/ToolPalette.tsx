// 工具面板组件 - 可折叠分类工具列表，支持拖拽到画布创建节点
import { useState, useEffect, useMemo } from 'react'
import type { ReactElement } from 'react'
import {
  Zap,
  Database,
  Brain,
  Settings,
  Send,
  Shuffle,
  Wrench,
  ChevronLeft,
  ChevronDown,
  TriangleAlert,
  Boxes,
  Search,
  Clock,
} from 'lucide-react'
import { getTools } from '../services/api'
import type { Tool } from '../types/workflow'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { Card, CardHeader, CardContent } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import {
  Collapsible,
  CollapsibleTrigger,
  CollapsibleContent,
} from '@/components/ui/Collapsible'
import { cn } from '@/lib/utils'

// localStorage key：用户最近使用的工具
const FAVORITE_TOOLS_KEY = 'flowgenie-favorite-tools'
const FAVORITE_MAX = 5

// 分类元信息：图标 + 显示名
const CATEGORY_META: Record<string, { icon: ReactElement; label: string }> = {
  触发: { icon: <Zap size={16} />, label: '触发' },
  数据获取: { icon: <Database size={16} />, label: '数据获取' },
  AI处理: { icon: <Brain size={16} />, label: 'AI 处理' },
  数据处理: { icon: <Settings size={16} />, label: '数据处理' },
  输出推送: { icon: <Send size={16} />, label: '输出推送' },
  逻辑控制: { icon: <Shuffle size={16} />, label: '逻辑控制' },
}

// 分类展示顺序（触发 → 数据获取 → AI处理 → 数据处理 → 输出推送 → 逻辑控制）
const CATEGORY_PRIORITY: Record<string, number> = {
  触发: 0,
  数据获取: 1,
  AI处理: 2,
  数据处理: 3,
  输出推送: 4,
  逻辑控制: 5,
}

// 将 hex 颜色转为低透明度 rgba，作为卡片浅色背景（适配深色主题）
function tintColor(hex: string, alpha = 0.15): string {
  if (!hex) return `hsl(var(--primary) / ${alpha})`
  let h = hex.replace('#', '')
  if (h.length === 3) {
    h = h
      .split('')
      .map((c) => c + c)
      .join('')
  }
  const r = parseInt(h.slice(0, 2), 16)
  const g = parseInt(h.slice(2, 4), 16)
  const b = parseInt(h.slice(4, 6), 16)
  if ([r, g, b].some(Number.isNaN)) return `hsl(var(--primary) / ${alpha})`
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

// 从 localStorage 读取 favorites（容错处理）
function loadFavorites(): string[] {
  try {
    const raw = localStorage.getItem(FAVORITE_TOOLS_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.filter((x) => typeof x === 'string').slice(0, FAVORITE_MAX)
  } catch {
    return []
  }
}

export function ToolPalette() {
  const [tools, setTools] = useState<Tool[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [collapsed, setCollapsed] = useState(false)
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(
    new Set()
  )
  const [searchQuery, setSearchQuery] = useState('')
  const [favorites, setFavorites] = useState<string[]>(() => loadFavorites())

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getTools()
      .then((data) => {
        if (!cancelled) {
          setTools(data)
          setError('')
        }
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : '加载工具失败')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  // 按 category 分组并按预定顺序排序
  const grouped = useMemo(() => {
    const map = new Map<string, Tool[]>()
    for (const t of tools) {
      const cat = t.category || '其他'
      if (!map.has(cat)) map.set(cat, [])
      map.get(cat)!.push(t)
    }
    return Array.from(map.entries()).sort(
      (a, b) => (CATEGORY_PRIORITY[a[0]] ?? 99) - (CATEGORY_PRIORITY[b[0]] ?? 99)
    )
  }, [tools])

  // 搜索过滤结果（扁平列表，跨分类匹配）
  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    if (!q) return []
    return tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.display_name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q)
    )
  }, [tools, searchQuery])

  // Favorites 对应的 Tool 对象列表（按 favorites 顺序，过滤掉不存在的）
  const favoriteTools = useMemo(() => {
    if (favorites.length === 0) return []
    const byName = new Map(tools.map((t) => [t.name, t]))
    return favorites
      .map((name) => byName.get(name))
      .filter((t): t is Tool => Boolean(t))
  }, [favorites, tools])

  // 切换分类折叠状态（Collapsible open=true 表示展开）
  const handleCategoryOpenChange = (cat: string, open: boolean) => {
    setCollapsedCategories((prev) => {
      const next = new Set(prev)
      if (open) next.delete(cat)
      else next.add(cat)
      return next
    })
  }

  // 搜索框值变化：清空折叠状态以展开所有分类（让用户看到所有匹配结果）
  const handleSearchChange = (value: string) => {
    setSearchQuery(value)
    if (value.trim()) {
      setCollapsedCategories(new Set())
    }
  }

  // 记录最近使用工具到 favorites
  const recordFavorite = (name: string) => {
    setFavorites((prev) => {
      const next = [name, ...prev.filter((n) => n !== name)].slice(
        0,
        FAVORITE_MAX
      )
      try {
        localStorage.setItem(FAVORITE_TOOLS_KEY, JSON.stringify(next))
      } catch {
        // 忽略写入失败（隐私模式/空间不足等）
      }
      return next
    })
  }

  // 渲染单个工具按钮（分类内 / Favorites / 搜索结果共用样式）
  const renderToolButton = (tool: Tool) => (
    <Button
      key={tool.name}
      variant="ghost"
      size="sm"
      className="h-auto w-full flex-col items-start gap-0.5 py-2 text-left transition-all duration-150 hover:border-primary/40 hover:bg-accent/50"
      draggable
      onDragStart={(e) => {
        e.dataTransfer.setData(
          'application/reactflow',
          JSON.stringify(tool)
        )
        e.dataTransfer.effectAllowed = 'move'
        recordFavorite(tool.name)
      }}
      onClick={() => recordFavorite(tool.name)}
      style={{ background: tintColor(tool.color) }}
      title={tool.description}
    >
      <span className="flex items-center gap-2">
        {tool.icon ? <span className="text-base">{tool.icon}</span> : <Wrench className="h-4 w-4" />}
        <span className="text-sm font-medium">{tool.display_name}</span>
      </span>
      <span className="text-xs text-muted-foreground line-clamp-2">
        {tool.description}
      </span>
    </Button>
  )

  // 折叠态：仅显示展开按钮
  if (collapsed) {
    return (
      <div className="flex h-full flex-col items-center justify-center border-r border-border p-2">
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9"
          onClick={() => setCollapsed(false)}
          title="展开工具箱"
          aria-label="展开工具箱"
        >
          <Wrench size={20} />
        </Button>
      </div>
    )
  }

  const isSearching = searchQuery.trim().length > 0

  return (
    <div className="flex h-full flex-col">
      <div
        className="flex shrink-0 cursor-pointer items-center justify-between border-b border-border p-3"
        onClick={() => setCollapsed(true)}
        title="折叠工具箱"
        role="button"
        aria-label="折叠工具箱"
      >
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Wrench size={18} /> 工具箱
        </span>
        <ChevronLeft size={16} className="text-muted-foreground" />
      </div>

      {/* 搜索框 */}
      <div className="relative shrink-0 border-b border-border p-2">
        <Search
          size={14}
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          type="text"
          value={searchQuery}
          onChange={(e) => handleSearchChange(e.target.value)}
          placeholder="搜索工具..."
          className="h-8 pl-7 text-xs"
          aria-label="搜索工具"
        />
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-2">
        {loading && (
          <div className="flex flex-col gap-2">
            {Array.from({ length: 4 }).map((_, i) => (
              <SkeletonCard key={i} />
            ))}
          </div>
        )}
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 p-2 text-xs text-destructive">
            <TriangleAlert size={16} /> {error}
          </div>
        )}
        {!loading && !error && tools.length === 0 && (
          <EmptyState
            icon={<Boxes size={24} />}
            title="暂无工具"
            description="工具加载完成后将在此显示"
          />
        )}

        {/* 搜索模式：扁平结果列表 */}
        {isSearching && !loading && !error && (
          <div className="flex flex-col gap-1">
            {searchResults.length === 0 ? (
              <EmptyState
                icon={<Search size={24} />}
                title="无匹配工具"
                description="尝试更换关键词"
              />
            ) : (
              searchResults.map(renderToolButton)
            )}
          </div>
        )}

        {/* 非搜索模式：Favorites + 分类列表 */}
        {!isSearching && !loading && !error && tools.length > 0 && (
          <>
            {favoriteTools.length > 0 && (
              <Card className="mb-2">
                <CardHeader className="flex items-center justify-between space-y-0 p-2.5">
                  <span className="flex items-center gap-2 text-sm font-medium">
                    <span className="text-primary">
                      <Clock size={16} />
                    </span>
                    最近使用
                    <Badge variant="secondary" className="text-[10px]">
                      {favoriteTools.length}
                    </Badge>
                  </span>
                </CardHeader>
                <CardContent className="flex flex-col gap-1 p-2 pt-0">
                  {favoriteTools.map(renderToolButton)}
                </CardContent>
              </Card>
            )}

            {grouped.map(([cat, items]) => {
              const meta = CATEGORY_META[cat] || {
                icon: <Wrench size={16} />,
                label: cat,
              }
              const isCatCollapsed = collapsedCategories.has(cat)
              return (
                <Card key={cat} className="mb-2">
                  <Collapsible
                    open={!isCatCollapsed}
                    onOpenChange={(open) =>
                      handleCategoryOpenChange(cat, open)
                    }
                  >
                    <CollapsibleTrigger asChild>
                      <CardHeader className="flex cursor-pointer flex-row items-center justify-between space-y-0 p-2.5">
                        <span className="flex items-center gap-2 text-sm font-medium">
                          <span className="text-primary">{meta.icon}</span>
                          {meta.label}
                          <Badge variant="secondary" className="text-[10px]">
                            {items.length}
                          </Badge>
                        </span>
                        <ChevronDown
                          size={14}
                          className={cn(
                            'text-muted-foreground transition-transform',
                            !isCatCollapsed && 'rotate-180'
                          )}
                        />
                      </CardHeader>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      <CardContent className="flex flex-col gap-1 p-2 pt-0">
                        {items.map(renderToolButton)}
                      </CardContent>
                    </CollapsibleContent>
                  </Collapsible>
                </Card>
              )
            })}
          </>
        )}
      </div>
    </div>
  )
}
