// 模板浏览页 - 以卡片网格展示所有场景模板，支持分类筛选与关键词搜索
import { useMemo, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Search, ArrowRight, LayoutGrid } from 'lucide-react'
import { SCENARIO_TEMPLATES } from './ScenarioTemplates'
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { EmptyState } from '@/components/ui/EmptyState'
import { cn } from '@/lib/utils'

// 分类列表：'全部' + 6 个业务分类
const CATEGORIES = [
  '全部',
  '新闻资讯',
  '销售报表',
  '开发运维',
  '数据分析',
  '通讯推送',
  '监控告警',
] as const

interface TemplatesViewProps {
  onUseTemplate: (requirement: string) => void // 切换到 editor + 填入 requirement
}

export function TemplatesView({ onUseTemplate }: TemplatesViewProps) {
  const [selectedCategory, setSelectedCategory] = useState<string>('全部')
  const [searchQuery, setSearchQuery] = useState('')

  // 分类 → 模板数："全部" 显示总数 15
  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { 全部: SCENARIO_TEMPLATES.length }
    for (const t of SCENARIO_TEMPLATES) {
      counts[t.category] = (counts[t.category] ?? 0) + 1
    }
    return counts
  }, [])

  // 过滤：先按 category（"全部" 不筛选），再按 searchQuery（匹配 title / description / requirement，大小写不敏感）
  const filteredTemplates = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return SCENARIO_TEMPLATES.filter((t) => {
      if (selectedCategory !== '全部' && t.category !== selectedCategory) return false
      if (!q) return true
      return (
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.requirement.toLowerCase().includes(q)
      )
    })
  }, [selectedCategory, searchQuery])

  return (
    <div className="flex h-full flex-col">
      {/* 顶部标题 + 搜索框 */}
      <div className="flex shrink-0 items-center justify-between gap-3 p-4 pb-0">
        <div className="flex items-center gap-2">
          <LayoutGrid size={20} className="text-primary" />
          <h2 className="text-xl font-semibold text-foreground">模板库</h2>
        </div>
        <div className="relative w-full max-w-xs">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground"
          />
          <Input
            type="text"
            className="pl-8"
            placeholder="搜索模板..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">
            共 {SCENARIO_TEMPLATES.length} 个
          </span>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        {/* 左侧分类筛选：固定宽度 160px，移动端隐藏 */}
        <aside className="hidden w-0 flex-col gap-1 overflow-y-auto p-3 md:flex md:w-[160px]">
          <div className="px-2 pb-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            分类
          </div>
          {CATEGORIES.map((cat) => {
            const active = selectedCategory === cat
            return (
              <Button
                key={cat}
                variant="ghost"
                className={cn(
                  'relative h-8 justify-between px-2',
                  active &&
                    'bg-primary/10 text-primary hover:bg-primary/10 hover:text-primary'
                )}
                onClick={() => setSelectedCategory(cat)}
              >
                {/* 激活态左边紫色条 */}
                {active && (
                  <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-primary" />
                )}
                <span>{cat}</span>
                <Badge variant="secondary">{categoryCounts[cat] ?? 0}</Badge>
              </Button>
            )
          })}
        </aside>

        {/* 右侧模板卡片网格：可垂直滚动 */}
        <div className="min-w-0 flex-1 overflow-y-auto p-4 pb-20 md:pb-4">
          {filteredTemplates.length === 0 ? (
            <div className="flex h-full items-center justify-center">
              <EmptyState
                icon={<LayoutGrid size={24} />}
                title="无匹配模板"
                description="尝试更换关键词或分类"
              />
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              <AnimatePresence mode="popLayout">
                {filteredTemplates.map((t, index) => (
                  <motion.div
                    key={t.key}
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.9 }}
                    transition={{ duration: 0.25, delay: index * 0.03 }}
                    whileHover={{ scale: 1.01, transition: { duration: 0.15 } }}
                  >
                    <Card className="group relative transition-colors hover:border-primary/60">
                      {/* 顶部：图标 */}
                      <CardHeader className="p-3 pb-2">
                        <t.icon className="h-7 w-7 text-primary" />
                      </CardHeader>
                      {/* hover 图标按钮 */}
                      <Button
                        variant="default"
                        size="icon"
                        onClick={() => onUseTemplate(t.requirement)}
                        className="absolute right-3 top-3 h-7 w-7 opacity-0 transition-opacity group-hover:opacity-100"
                        aria-label="使用此模板"
                      >
                        <ArrowRight className="h-4 w-4" />
                      </Button>
                      <CardContent className="flex flex-col gap-2 p-3 pt-2">
                        <div className="flex items-center justify-between gap-2">
                          <CardTitle className="text-base font-medium leading-snug">
                            {t.title}
                          </CardTitle>
                          <Badge variant="outline" className="shrink-0 text-xs">{t.category}</Badge>
                        </div>
                        <CardDescription className="text-sm">
                          {t.description}
                        </CardDescription>
                      </CardContent>
                    </Card>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
