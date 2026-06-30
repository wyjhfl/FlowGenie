// 命令面板 - 基于 cmdk + Radix Dialog，⌘K 唤起，支持键盘导航
import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Command as CommandPrimitive } from 'cmdk'
import {
  ChartColumn,
  Clock,
  FileDown,
  History,
  Key,
  Moon,
  Plus,
  Search,
} from 'lucide-react'
import type { ComponentType } from 'react'

export interface CommandProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  workflows: Array<{ id: string; name: string; scenario: string }>
  onLoadWorkflow: (id: string) => void
  onNewWorkflow: () => void
  onToggleTheme: () => void
  onNavigate: (panel: 'credentials' | 'schedule' | 'dashboard' | 'export' | 'history') => void
}

type NavPanel = 'credentials' | 'schedule' | 'dashboard' | 'export' | 'history'

// 导航命令配置：面板键 → 中文标签 + 图标
const NAV_COMMANDS: Array<{
  panel: NavPanel
  label: string
  icon: ComponentType<{ className?: string }>
}> = [
  { panel: 'credentials', label: '凭证管理', icon: Key },
  { panel: 'schedule', label: '定时调度', icon: Clock },
  { panel: 'dashboard', label: '数据统计', icon: ChartColumn },
  { panel: 'export', label: '导出工作流', icon: FileDown },
  { panel: 'history', label: '运行历史', icon: History },
]

// 命令项统一样式
const ITEM_CLASS =
  'flex items-center gap-2 rounded-md px-3 py-2 text-sm text-foreground cursor-pointer aria-selected:bg-primary/10 aria-selected:text-primary'

// 分组标题样式
function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-3 py-1.5 text-xs font-medium text-muted-foreground">{children}</div>
  )
}

export function Command({
  open,
  onOpenChange,
  workflows,
  onLoadWorkflow,
  onNewWorkflow,
  onToggleTheme,
  onNavigate,
}: CommandProps) {
  const close = () => onOpenChange(false)

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        {/* 背景遮罩 */}
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-background/70 backdrop-blur-sm" />
        {/* 容器：居中 + 顶部留白 15vh */}
        <DialogPrimitive.Content
          className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]"
          onPointerDown={(e) => {
            // 点击面板外空白区域关闭（Esc 由 Radix 自动处理）
            if (e.target === e.currentTarget) close()
          }}
        >
          <CommandPrimitive
            label="FlowGenie 命令面板"
            loop
            className="flex w-full max-w-xl flex-col overflow-hidden rounded-xl border border-border bg-card/95 shadow-2xl backdrop-blur-xl"
          >
          {/* 顶部搜索框 */}
            <div className="flex items-center gap-2 border-b border-border px-4">
              <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
              <CommandPrimitive.Input
                placeholder="搜索工作流或输入命令..."
                className="flex-1 bg-transparent py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
            </div>

            {/* 命令列表 */}
            <CommandPrimitive.List className="max-h-[400px] overflow-y-auto p-2">
              <CommandPrimitive.Empty className="py-6 text-center text-sm text-muted-foreground">
                无匹配结果
              </CommandPrimitive.Empty>

              {/* 工作流分组 */}
              {workflows.length > 0 && (
                <CommandPrimitive.Group heading={<GroupHeading>工作流</GroupHeading>}>
                  {workflows.map((w) => (
                    <CommandPrimitive.Item
                      key={w.id}
                      value={`workflow ${w.name} ${w.scenario}`}
                      onSelect={() => {
                        onLoadWorkflow(w.id)
                        close()
                      }}
                      className={ITEM_CLASS}
                    >
                      <span className="flex-1 truncate">{w.name}</span>
                      <span className="truncate text-xs text-muted-foreground">{w.scenario}</span>
                    </CommandPrimitive.Item>
                  ))}
                </CommandPrimitive.Group>
              )}

              {/* 操作分组 */}
              <CommandPrimitive.Group heading={<GroupHeading>操作</GroupHeading>}>
                <CommandPrimitive.Item
                  value="新建工作流 new create"
                  onSelect={() => {
                    onNewWorkflow()
                    close()
                  }}
                  className={ITEM_CLASS}
                >
                  <Plus className="h-4 w-4" />
                  <span>新建工作流</span>
                </CommandPrimitive.Item>
              </CommandPrimitive.Group>

              {/* 导航分组 */}
              <CommandPrimitive.Group heading={<GroupHeading>导航</GroupHeading>}>
                {NAV_COMMANDS.map(({ panel, label, icon: Icon }) => (
                  <CommandPrimitive.Item
                    key={panel}
                    value={`navigate ${label}`}
                    onSelect={() => {
                      onNavigate(panel)
                      close()
                    }}
                    className={ITEM_CLASS}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{label}</span>
                  </CommandPrimitive.Item>
                ))}
              </CommandPrimitive.Group>

              {/* 主题分组 */}
              <CommandPrimitive.Group heading={<GroupHeading>主题</GroupHeading>}>
                <CommandPrimitive.Item
                  value="切换主题 theme dark light"
                  onSelect={() => {
                    onToggleTheme()
                    close()
                  }}
                  className={ITEM_CLASS}
                >
                  <Moon className="h-4 w-4" />
                  <span>切换主题</span>
                </CommandPrimitive.Item>
              </CommandPrimitive.Group>
            </CommandPrimitive.List>
          </CommandPrimitive>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
