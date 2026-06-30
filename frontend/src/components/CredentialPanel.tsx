// 凭证配置面板 - 管理各工具的凭证（API Key / Token 等），按类别分组展示
import { useState, useEffect, type ReactNode } from 'react'
import {
  RefreshCw,
  Loader,
  X,
  CircleCheck,
  CircleX,
  TriangleAlert,
  Key,
  Eye,
  EyeOff,
  Mail,
  MessageSquare,
  Bot,
  FileText,
  Send,
  Bell,
  Database,
  Code2,
} from 'lucide-react'
import {
  getCredentials,
  updateCredential,
  testCredential,
  type CredentialItem,
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

interface Props {
  onClose: () => void
}

interface TestResult {
  success: boolean
  message: string
}

// 保存成功后用于回显的脱敏占位符
const MASKED_PLACEHOLDER = '••••••••'

// 分组图标映射(缺省用 Key 图标),提升各凭证类别辨识度
const CATEGORY_ICON: Record<string, ReactNode> = {
  '邮件': <Mail size={14} />,
  'IM推送': <MessageSquare size={14} />,
  'LLM': <Bot size={14} />,
  'Notion': <FileText size={14} />,
  '飞书': <Send size={14} />,
  '通知': <Bell size={14} />,
  '开发工具': <Code2 size={14} />,
  '数据库': <Database size={14} />,
}

export function CredentialPanel({ onClose }: Props) {
  const [credentials, setCredentials] = useState<CredentialItem[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [values, setValues] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState<Record<string, boolean>>({})
  const [testing, setTesting] = useState<Record<string, boolean>>({})
  const [testResults, setTestResults] = useState<Record<string, TestResult>>({})
  const [actionError, setActionError] = useState<Record<string, string>>({})
  // secret 类型凭证的明文可见性（按 key 记录可见状态）
  const [visibleSecrets, setVisibleSecrets] = useState<Set<string>>(new Set())
  const toast = useToast()

  // 切换某凭证的密码可见性
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
      const list = await getCredentials()
      setCredentials(list)
      const initValues: Record<string, string> = {}
      for (const c of list) {
        // secret 类型且已配置的凭证不填充脱敏值，避免误存
        if (c.type === 'secret' && c.configured) {
          initValues[c.key] = ''
        } else {
          initValues[c.key] = c.value
        }
      }
      setValues(initValues)
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : '加载凭证失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
  }, [])

  const handleSave = async (key: string) => {
    const val = values[key] ?? ''
    if (val === MASKED_PLACEHOLDER || !val) return // 占位符或空值不保存
    setSaving((p) => ({ ...p, [key]: true }))
    setActionError((p) => ({ ...p, [key]: '' }))
    try {
      await updateCredential(key, val)
      // 局部更新：标记为已配置，输入框清空，避免全量刷新覆盖其他未保存输入
      setCredentials((prev) =>
        prev.map((c) => (c.key === key ? { ...c, configured: true, value: MASKED_PLACEHOLDER } : c))
      )
      setValues((p) => ({ ...p, [key]: '' })) // 清空输入框
      toast.success('凭证已保存')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '保存失败'
      setActionError((p) => ({
        ...p,
        [key]: msg,
      }))
      toast.error(msg)
    } finally {
      setSaving((p) => ({ ...p, [key]: false }))
    }
  }

  const handleTest = async (key: string) => {
    setTesting((p) => ({ ...p, [key]: true }))
    setTestResults((p) => ({ ...p, [key]: { success: false, message: '测试中...' } }))
    try {
      const result = await testCredential(key)
      setTestResults((p) => ({ ...p, [key]: result }))
      if (result.success) toast.success('测试通过')
      else toast.error(result.message || '测试失败')
    } catch (e) {
      const msg = e instanceof Error ? e.message : '测试失败'
      setTestResults((p) => ({
        ...p,
        [key]: { success: false, message: msg },
      }))
      toast.error(msg)
    } finally {
      setTesting((p) => ({ ...p, [key]: false }))
    }
  }

  // 按 category 分组，保留首次出现顺序
  const grouped: { category: string; items: CredentialItem[] }[] = []
  const indexMap: Record<string, number> = {}
  for (const c of credentials) {
    if (c.category in indexMap) {
      grouped[indexMap[c.category]].items.push(c)
    } else {
      indexMap[c.category] = grouped.length
      grouped.push({ category: c.category, items: [c] })
    }
  }

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部工具条：刷新 / 关闭 */}
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-lg font-semibold">凭证配置</h3>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            onClick={refresh}
            disabled={loading}
            title="刷新"
            aria-label="刷新凭证列表"
          >
            {loading ? <Loader size={16} className="animate-spin" /> : <RefreshCw size={16} />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={onClose}
            title="关闭"
            aria-label="关闭凭证面板"
          >
            <X size={16} />
          </Button>
        </div>
      </div>

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
          icon={<Key size={24} />}
          title="暂未配置凭证"
          description="工具运行所需的 API Key / Token 将在此配置"
        />
      ) : (
        <div className="flex flex-col gap-4">
          {grouped.map((group) => (
            <div key={group.category} className="flex flex-col gap-2">
              <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {CATEGORY_ICON[group.category] ?? <Key size={14} />}
                <span>{group.category}</span>
              </div>
              <div className="flex flex-col gap-2">
                {group.items.map((c) => (
                  <Card key={c.key}>
                    <CardHeader className="pb-2">
                      <div className="flex items-center justify-between gap-2">
                        <CardTitle className="text-sm">{c.display_name}</CardTitle>
                        <Badge
                          variant={c.configured ? 'success' : 'warning'}
                          className="gap-1"
                        >
                          {c.configured ? (
                            <>
                              <CircleCheck size={12} /> 已配置
                            </>
                          ) : (
                            <>
                              <TriangleAlert size={12} /> 未配置
                            </>
                          )}
                        </Badge>
                      </div>
                    </CardHeader>
                    <CardContent className="flex flex-col gap-2">
                      <div className="flex items-center gap-2">
                        <div className="relative flex-1">
                          <Input
                            type={
                              c.type === 'secret'
                                ? visibleSecrets.has(c.key)
                                  ? 'text'
                                  : 'password'
                                : 'text'
                            }
                            value={values[c.key] ?? ''}
                            onChange={(e) => {
                              setValues((p) => ({ ...p, [c.key]: e.target.value }))
                              // 输入变更时清除旧错误与测试结果
                              setActionError((p) => ({ ...p, [c.key]: '' }))
                              setTestResults((p) => {
                                const next = { ...p }
                                delete next[c.key]
                                return next
                              })
                            }}
                            placeholder={c.type === 'secret' ? '输入新值以更新' : '请输入值'}
                            className={c.type === 'secret' ? 'pr-10' : ''}
                          />
                          {c.type === 'secret' && (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon"
                              className="absolute right-0 top-0 h-10 w-10"
                              title={visibleSecrets.has(c.key) ? '隐藏' : '显示'}
                              aria-label={
                                visibleSecrets.has(c.key) ? '隐藏密码' : '显示密码'
                              }
                              onClick={() => toggleSecretVisible(c.key)}
                            >
                              {visibleSecrets.has(c.key) ? (
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
                          onClick={() => handleSave(c.key)}
                          disabled={saving[c.key] || !values[c.key] || values[c.key] === MASKED_PLACEHOLDER}
                        >
                          {saving[c.key] ? '保存中...' : '保存'}
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleTest(c.key)}
                          disabled={testing[c.key]}
                        >
                          {testing[c.key] ? '测试中...' : '测试'}
                        </Button>
                      </div>
                      {actionError[c.key] && (
                        <div className="flex items-center gap-1 text-xs text-destructive">
                          <TriangleAlert size={14} /> {actionError[c.key]}
                        </div>
                      )}
                      {testResults[c.key] && (
                        <Alert
                          variant={testResults[c.key].success ? 'default' : 'destructive'}
                        >
                          {testResults[c.key].success ? (
                            <CircleCheck size={16} />
                          ) : (
                            <CircleX size={16} />
                          )}
                          <AlertDescription>
                            {testResults[c.key].message}
                          </AlertDescription>
                        </Alert>
                      )}
                    </CardContent>
                  </Card>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
