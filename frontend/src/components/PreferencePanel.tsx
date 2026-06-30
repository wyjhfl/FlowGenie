// 偏好设置面板 - schema 驱动渲染用户偏好,支持自动填充工具参数
import { useState, useEffect } from 'react'
import {
  RefreshCw,
  Loader,
  X,
  CircleCheck,
  TriangleAlert,
  SlidersHorizontal,
  Eye,
  EyeOff,
  Trash2,
} from 'lucide-react'
import {
  getPreferences,
  getPreferenceSchema,
  updatePreferences,
  deletePreference,
  type PreferenceItem,
} from '../services/api'
import { SkeletonCard } from '@/components/ui/Skeleton'
import { EmptyState } from '@/components/ui/EmptyState'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
} from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Alert, AlertDescription } from '@/components/ui/Alert'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/Select'

interface Props {
  onClose: () => void
}

// secret 类型保存后用于回显的脱敏占位符
const MASKED_PLACEHOLDER = '••••••••'

export function PreferencePanel({ onClose }: Props) {
  const [schema, setSchema] = useState<PreferenceItem[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [actionError, setActionError] = useState<Record<string, string>>({})
  const [savedMsg, setSavedMsg] = useState<Record<string, boolean>>({})
  // secret 类型偏好的明文可见性(按 key 记录)
  const [visibleSecrets, setVisibleSecrets] = useState<Set<string>>(new Set())
  const toast = useToast()

  const toggleSecretVisible = (key: string) => {
    setVisibleSecrets((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  const refresh = async () => {
    setLoading(true)
    setLoadError('')
    try {
      const [schemaData, prefValues] = await Promise.all([
        getPreferenceSchema(),
        getPreferences(),
      ])
      setSchema(schemaData)
      const initValues: Record<string, string> = {}
      for (const item of schemaData) {
        // secret 类型且有值时不填充脱敏值,避免误存
        if (item.type === 'secret' && prefValues[item.key]) {
          initValues[item.key] = ''
        } else {
          initValues[item.key] = prefValues[item.key] || ''
        }
      }
      setValues(initValues)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : '加载偏好失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleSave = async (item: PreferenceItem) => {
    const val = values[item.key] ?? ''
    // secret 类型:空值或脱敏占位符不保存
    if (item.type === 'secret' && (val === MASKED_PLACEHOLDER || !val)) return
    setSaving((p) => ({ ...p, [item.key]: true }))
    setActionError((p) => ({ ...p, [item.key]: '' }))
    try {
      await updatePreferences({ [item.key]: val })
      // secret 类型保存后清空输入框,避免明文残留
      if (item.type === 'secret') {
        setValues((p) => ({ ...p, [item.key]: '' }))
      }
      setSavedMsg((p) => ({ ...p, [item.key]: true }))
      toast.success('偏好已保存')
      setTimeout(() => {
        setSavedMsg((p) => ({ ...p, [item.key]: false }))
      }, 2000)
    } catch (e) {
      const msg = e instanceof Error ? e.message : '保存失败'
      setActionError((p) => ({ ...p, [item.key]: msg }))
      toast.error(msg)
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }))
    }
  }

  const handleDelete = async (item: PreferenceItem) => {
    setSaving((p) => ({ ...p, [item.key]: true }))
    setActionError((p) => ({ ...p, [item.key]: '' }))
    try {
      await deletePreference(item.key)
      setValues((p) => ({ ...p, [item.key]: '' }))
      setSavedMsg((p) => ({ ...p, [item.key]: true }))
      toast.success('偏好已清除')
      setTimeout(() => {
        setSavedMsg((p) => ({ ...p, [item.key]: false }))
      }, 2000)
    } catch (e) {
      // 404 表示已不存在,视为成功
      const msg = e instanceof Error ? e.message : '清除失败'
      if (msg.includes('不存在') || msg.includes('404')) {
        setValues((p) => ({ ...p, [item.key]: '' }))
        toast.success('偏好已清除')
      } else {
        setActionError((p) => ({ ...p, [item.key]: msg }))
        toast.error(msg)
      }
    } finally {
      setSaving((p) => ({ ...p, [item.key]: false }))
    }
  }

  // 构建可填充工具参数的提示文字
  const buildApplicableHint = (item: PreferenceItem): string => {
    const applicable = item.applicable_tools || {}
    const entries = Object.entries(applicable)
    if (entries.length === 0) return ''
    const descs = entries.flatMap(([toolName, paramNames]) =>
      paramNames.map((pn) => `${toolName}.${pn}`)
    )
    return `将自动填充: ${descs.join(', ')}`
  }

  // 按 category 分组,保留首次出现顺序
  const grouped: { category: string; items: PreferenceItem[] }[] = []
  const indexMap: Record<string, number> = {}
  for (const item of schema) {
    if (item.category in indexMap) {
      grouped[indexMap[item.category]].items.push(item)
    } else {
      indexMap[item.category] = grouped.length
      grouped.push({ category: item.category, items: [item] })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部工具条:刷新 / 关闭 */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">偏好设置</h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={refresh}
            disabled={loading}
            title="刷新"
            aria-label="刷新偏好列表"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title="关闭"
            aria-label="关闭偏好面板"
          >
            <X size={16} />
          </Button>
        </div>
      </div>

      <Alert>
        <SlidersHorizontal size={16} />
        <AlertDescription>
          偏好值将在工作流执行时自动填充到对应工具参数(参数为空时回填,不覆盖显式设置的值)。也可在工作流中用 <code className="rounded bg-muted px-1">{'{{pref.key}}'}</code> 显式引用。
        </AlertDescription>
      </Alert>

      {loading ? (
        <div className="flex flex-col gap-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : loadError ? (
        <Alert variant="destructive">
          <TriangleAlert size={16} />
          <AlertDescription>{loadError}</AlertDescription>
        </Alert>
      ) : grouped.length === 0 ? (
        <EmptyState
          icon={<SlidersHorizontal size={24} />}
          title="暂无偏好项"
          description="偏好 schema 为空"
        />
      ) : (
        <div className="flex flex-col gap-4">
          {grouped.map((group) => (
            <div key={group.category} className="flex flex-col gap-2">
              <div className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.category}
              </div>
              <div className="flex flex-col gap-2">
                {group.items.map((item) => {
                  const hint = buildApplicableHint(item)
                  return (
                    <Card key={item.key}>
                      <CardHeader className="pb-2">
                        <div className="flex items-center justify-between gap-2">
                          <CardTitle className="text-sm">{item.display_name}</CardTitle>
                          {values[item.key] && (
                            <Badge variant="success" className="gap-1">
                              <CircleCheck size={12} /> 已配置
                            </Badge>
                          )}
                        </div>
                      </CardHeader>
                      <CardContent className="flex flex-col gap-2">
                        <div className="flex items-center gap-2">
                          <div className="relative flex-1">
                            {item.type === 'select' ? (
                              <Select
                                value={values[item.key] || item.default}
                                onValueChange={(v) => {
                                  setValues((p) => ({ ...p, [item.key]: v }))
                                  setActionError((p) => ({ ...p, [item.key]: '' }))
                                  setSavedMsg((p) => ({ ...p, [item.key]: false }))
                                }}
                              >
                                <SelectTrigger className="flex-1">
                                  <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                  {(item.options || []).map((opt) => (
                                    <SelectItem key={opt} value={opt}>
                                      {opt}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            ) : (
                              <Input
                                type={
                                  item.type === 'secret'
                                    ? visibleSecrets.has(item.key)
                                      ? 'text'
                                      : 'password'
                                    : item.type === 'number'
                                    ? 'number'
                                    : 'text'
                                }
                                value={values[item.key] ?? ''}
                                onChange={(e) => {
                                  setValues((p) => ({ ...p, [item.key]: e.target.value }))
                                  setActionError((p) => ({ ...p, [item.key]: '' }))
                                  setSavedMsg((p) => ({ ...p, [item.key]: false }))
                                }}
                                placeholder={
                                  item.type === 'secret'
                                    ? '输入新值以更新'
                                    : item.default
                                    ? `默认: ${item.default}`
                                    : '请输入值'
                                }
                                className={item.type === 'secret' ? 'pr-10' : ''}
                              />
                            )}
                            {item.type === 'secret' && (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon"
                                className="absolute right-0 top-0 h-10 w-10"
                                title={visibleSecrets.has(item.key) ? '隐藏' : '显示'}
                                aria-label={
                                  visibleSecrets.has(item.key) ? '隐藏' : '显示'
                                }
                                onClick={() => toggleSecretVisible(item.key)}
                              >
                                {visibleSecrets.has(item.key) ? (
                                  <EyeOff size={14} />
                                ) : (
                                  <Eye size={14} />
                                )}
                              </Button>
                            )}
                          </div>
                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handleSave(item)}
                            disabled={
                              saving[item.key] ||
                              (item.type === 'secret' &&
                                (!values[item.key] ||
                                  values[item.key] === MASKED_PLACEHOLDER))
                            }
                          >
                            {saving[item.key] ? '保存中...' : '保存'}
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => handleDelete(item)}
                            disabled={saving[item.key] || !values[item.key]}
                            title="清除"
                            aria-label="清除偏好"
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                        {item.description && (
                          <div className="text-xs text-muted-foreground">
                            {item.description}
                          </div>
                        )}
                        {hint && (
                          <div className="text-xs text-primary/80">{hint}</div>
                        )}
                        {actionError[item.key] && (
                          <div className="flex items-center gap-1 text-xs text-destructive">
                            <TriangleAlert size={14} /> {actionError[item.key]}
                          </div>
                        )}
                        {savedMsg[item.key] && (
                          <div className="flex items-center gap-1 text-xs text-success">
                            <CircleCheck size={14} /> 已保存
                          </div>
                        )}
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
