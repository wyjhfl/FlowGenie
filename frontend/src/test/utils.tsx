// 测试工具:自定义 render 包裹必要的 Provider(ThemeProvider 等)
import { render, type RenderOptions } from '@testing-library/react'
import type { ReactElement, ReactNode } from 'react'

// 如需包裹全局 Provider(如 ToastProvider/ThemeProvider),在此处添加
// 当前 DashboardPanel 等组件无强依赖的全局 Provider,直接渲染即可
function AllProviders({ children }: { children: ReactNode }) {
  return <>{children}</>
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, 'wrapper'>
) {
  return render(ui, { wrapper: AllProviders, ...options })
}

export { render }
