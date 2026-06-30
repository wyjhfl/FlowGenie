// 全局键盘快捷键注册(从 App.tsx 抽出)
// ⌘K/Ctrl+K 唤起命令面板;T 切换工具箱;I 移动端唤起 inspector;
// Ctrl/Cmd+Z 撤销;Ctrl/Cmd+Shift+Z 或 Ctrl+Y 重做。
import { useEffect } from 'react'

export interface KeyboardShortcutHandlers {
  onOpenCommandPalette: () => void
  onToggleToolPalette: () => void
  onToggleMobileInspector: () => void
  onUndo: () => void
  onRedo: () => void
}

function isEditableTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  return (
    el.tagName === 'INPUT' ||
    el.tagName === 'TEXTAREA' ||
    el.isContentEditable
  )
}

export function useKeyboardShortcuts(handlers: KeyboardShortcutHandlers) {
  const {
    onOpenCommandPalette,
    onToggleToolPalette,
    onToggleMobileInspector,
    onUndo,
    onRedo,
  } = handlers

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // ⌘K / Ctrl+K 唤起命令面板(不受输入框限制)
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        onOpenCommandPalette()
        return
      }

      const inEditable = isEditableTarget(e.target)

      // 撤销/重做:在输入框/文本域/可编辑区域内不触发
      const isUndo = (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey
      const isRedo = (e.ctrlKey || e.metaKey) && (
        (e.key.toLowerCase() === 'z' && e.shiftKey) || e.key.toLowerCase() === 'y'
      )
      if (isUndo || isRedo) {
        if (inEditable) return
        e.preventDefault()
        if (isUndo) onUndo()
        else onRedo()
        return
      }

      // 单字符快捷键:避免在输入框/文本域/可编辑区域内触发
      if (inEditable) return
      // 输入法组合中(中文/日文等)不触发单字符快捷键,避免误触
      if (e.isComposing || e.keyCode === 229) return
      if (e.key === 't' || e.key === 'T') {
        e.preventDefault()
        onToggleToolPalette()
      } else if (e.key === 'i' || e.key === 'I') {
        // 桌面端 inspector 由选中节点唤起;仅移动端保留 I 键唤起底部 Sheet
        if (window.innerWidth < 768) {
          e.preventDefault()
          onToggleMobileInspector()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [
    onOpenCommandPalette,
    onToggleToolPalette,
    onToggleMobileInspector,
    onUndo,
    onRedo,
  ])
}
