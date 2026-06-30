// 左侧细 sidebar 导航 - 64px 宽，纯黑底 + 紫色激活态
import {
  Workflow,
  Key,
  Clock,
  ChartColumn,
  FileDown,
  History,
  Sun,
  Moon,
  LayoutDashboard,
  LayoutGrid,
  SlidersHorizontal,
} from 'lucide-react'
import type { ComponentType } from 'react'
import { Button } from '@/components/ui/Button'
import { Separator } from '@/components/ui/Separator'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/Tooltip'
import { cn } from '@/lib/utils'

export type SidebarPanel =
  | 'dashboard'
  | 'editor'
  | 'templates'
  | 'workflows'
  | 'credentials'
  | 'preferences'
  | 'schedule'
  | 'dashboard-stats'
  | 'export'
  | 'history'

export interface SidebarProps {
  activePanel: SidebarPanel
  onPanelChange: (panel: SidebarPanel) => void
  theme: 'dark' | 'light'
  onThemeToggle: () => void
}

// 顶部视图切换项：视图键 → 图标 + 中文标签
const VIEW_ITEMS: Array<{
  key: SidebarPanel
  label: string
  icon: ComponentType<{ className?: string }>
}> = [
  { key: 'dashboard', label: '仪表盘', icon: LayoutDashboard },
  { key: 'editor', label: '编辑器', icon: Workflow },
  { key: 'templates', label: '模板库', icon: LayoutGrid },
]

// 功能项配置：面板键 → 图标 + 中文标签
const NAV_ITEMS: Array<{
  key: SidebarPanel
  label: string
  icon: ComponentType<{ className?: string }>
}> = [
  { key: 'workflows', label: '工作流', icon: Workflow },
  { key: 'credentials', label: '凭证', icon: Key },
  { key: 'preferences', label: '偏好', icon: SlidersHorizontal },
  { key: 'schedule', label: '定时', icon: Clock },
  { key: 'dashboard-stats', label: '统计', icon: ChartColumn },
  { key: 'export', label: '导出', icon: FileDown },
  { key: 'history', label: '历史', icon: History },
]

export function Sidebar({
  activePanel,
  onPanelChange,
  theme,
  onThemeToggle,
}: SidebarProps) {
  return (
    <TooltipProvider delayDuration={300}>
      <aside className="hidden h-full w-16 flex-col border-r border-border bg-background md:flex">
        {/* 顶部 logo（高 48px 对齐 CommandBar），点击回到 workflows 面板 */}
        <button
          type="button"
          onClick={() => onPanelChange('workflows')}
          className="flex h-12 items-center justify-center"
          aria-label="FlowGenie 首页"
        >
          <span className="text-lg font-bold text-primary">FG</span>
        </button>

        {/* 中部导航 */}
        <nav className="flex min-h-0 flex-1 flex-col gap-1 p-2">
          {/* 顶部视图切换：仪表盘 / 编辑器 / 模板库 */}
          {VIEW_ITEMS.map(({ key, label, icon: Icon }) => {
            const active = activePanel === key
            return (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onPanelChange(key)}
                    aria-label={label}
                    className={cn(
                      'relative h-11 w-11 rounded-lg text-muted-foreground transition-all duration-150 hover:bg-accent hover:text-foreground hover:translate-x-0.5',
                      active &&
                        'bg-primary/15 text-primary hover:bg-primary/15 hover:text-primary before:content-[""] before:absolute before:left-0 before:top-1/2 before:h-7 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-primary'
                    )}
                  >
                    <div className="flex flex-col items-center gap-0.5">
                      <Icon className="h-5 w-5" />
                      <span className="text-[9px] font-medium leading-none">{label}</span>
                    </div>
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            )
          })}

          {/* 分隔线：视图切换 ↔ 功能图标 */}
          <Separator className="my-3" />

          {/* 功能图标：工作流 / 凭证 / 定时 / 统计 / 导出 / 历史 */}
          {NAV_ITEMS.map(({ key, label, icon: Icon }) => {
            const active = activePanel === key
            return (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => onPanelChange(key)}
                    aria-label={label}
                    className={cn(
                      'relative h-10 w-10 rounded-lg text-muted-foreground transition-all duration-150 hover:bg-accent hover:text-foreground hover:translate-x-0.5',
                      active &&
                        'bg-primary/10 text-primary hover:bg-primary/10 hover:text-primary before:content-[""] before:absolute before:left-0 before:top-1/2 before:h-6 before:w-0.5 before:-translate-y-1/2 before:rounded-full before:bg-primary'
                    )}
                  >
                    <Icon className="h-5 w-5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">{label}</TooltipContent>
              </Tooltip>
            )
          })}
        </nav>

        {/* 底部主题切换：dark 显示 Sun，light 显示 Moon */}
        <div className="p-2">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={onThemeToggle}
                aria-label="切换主题"
                className="h-10 w-10 rounded-lg text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
              >
                {theme === 'dark' ? (
                  <Sun className="h-5 w-5" />
                ) : (
                  <Moon className="h-5 w-5" />
                )}
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">
              {theme === 'dark' ? '亮色模式' : '暗色模式'}
            </TooltipContent>
          </Tooltip>
        </div>
      </aside>
    </TooltipProvider>
  )
}
