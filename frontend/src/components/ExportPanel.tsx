// 导出面板
import { useState } from 'react'
import { Copy, Download, FileDown, TriangleAlert } from 'lucide-react'
import type { ParseResponse } from '../types/workflow'
import { exportWorkflow } from '../services/api'
import { useToast } from '@/components/ui/Toast'
import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { Badge } from '@/components/ui/Badge'
import { Textarea } from '@/components/ui/Textarea'
import { Alert, AlertDescription } from '@/components/ui/Alert'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/Select'

interface Props {
  workflow: ParseResponse | null
}

export function ExportPanel({ workflow }: Props) {
  const [format, setFormat] = useState<'trae_skill' | 'trae_skill_yaml' | 'json' | 'python_script'>('trae_skill')
  const [preview, setPreview] = useState<string>('')
  const [exportError, setExportError] = useState(false)
  const [loading, setLoading] = useState(false)
  const [showPreview, setShowPreview] = useState(false)
  const [filename, setFilename] = useState<string>('')
  const [downloading, setDownloading] = useState(false)
  const toast = useToast()

  // 复制预览内容到剪贴板
  const handleCopy = async () => {
    if (!preview || exportError) return
    try {
      await navigator.clipboard.writeText(preview)
      toast.success('已复制到剪贴板')
    } catch {
      toast.error('复制失败，请手动复制')
    }
  }

  const handleFormatChange = (newFormat: typeof format) => {
    setFormat(newFormat)
    setPreview('')
    setExportError(false)
    setFilename('')
    setShowPreview(false)
  }

  const handleExport = async () => {
    if (!workflow) return
    setLoading(true)
    setShowPreview(true)
    try {
      const result = await exportWorkflow(workflow, format)
      setPreview(result.content)
      setFilename(result.filename)
      setExportError(false)
      toast.success('导出成功')
    } catch (e) {
      setPreview('导出失败：' + (e instanceof Error ? e.message : String(e)))
      setExportError(true)
      toast.error('导出失败')
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!preview || downloading) return
    setDownloading(true)
    try {
      const extMap: Record<string, string> = {
        trae_skill: 'json',
        trae_skill_yaml: 'yaml',
        json: 'json',
        python_script: 'py',
      }
      const contentTypeMap: Record<string, string> = {
        trae_skill: 'application/json',
        trae_skill_yaml: 'text/yaml',
        json: 'application/json',
        python_script: 'text/x-python',
      }
      const ext = extMap[format] || 'txt'
      const contentType = contentTypeMap[format] || 'text/plain;charset=utf-8'
      const blob = new Blob([preview], { type: contentType })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || `flowgenie_workflow.${ext}`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setDownloading(false)
    }
  }

  const formatLabels: Record<string, string> = {
    trae_skill: 'TRAE Skill (JSON)',
    trae_skill_yaml: 'TRAE Skill (YAML)',
    json: '通用 JSON',
    python_script: 'Python 脚本 (.py)',
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-base font-semibold">导出工作流</h3>
      <div className="flex flex-col gap-3">
        {!workflow ? (
          <EmptyState
            icon={<FileDown size={24} />}
            title="暂无工作流可导出"
            description="请先在编辑器中生成工作流"
          />
        ) : (
          <>
            {/* 工作流来源信息 */}
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant="info">{workflow.source}</Badge>
              <Badge variant="outline">{workflow.scenario}</Badge>
            </div>

            {/* 格式选择 + 导出 / 下载按钮 */}
            <div className="flex flex-wrap items-center gap-2">
              <Select
                value={format}
                onValueChange={(v) => handleFormatChange(v as typeof format)}
              >
                <SelectTrigger className="w-[200px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(formatLabels).map(([k, v]) => (
                    <SelectItem key={k} value={k}>
                      {v}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Button onClick={handleExport} disabled={loading}>
                  <FileDown size={16} />
                  {loading ? '导出中...' : '生成导出'}
              </Button>
              {/* 下载按钮仅在导出成功后显示 */}
              {preview && !exportError && (
                <Button variant="secondary" onClick={handleDownload} disabled={downloading}>
                  <Download size={16} /> 下载文件
                </Button>
              )}
            </div>

            {/* 预览区 / 错误提示 */}
            {showPreview && (
              exportError ? (
                <Alert variant="destructive">
                  <TriangleAlert size={16} />
                  <AlertDescription>{preview}</AlertDescription>
                </Alert>
              ) : (
                <div className="flex flex-col gap-2">
                  <div className="flex items-center justify-between gap-2">
                    <h4 className="text-sm font-medium">预览</h4>
                    {preview && !exportError && (
                      <Button
                        variant="outline"
                        size="sm"
                        title="复制预览内容"
                        aria-label="复制预览内容到剪贴板"
                        onClick={handleCopy}
                      >
                        <Copy size={14} /> 复制
                      </Button>
                    )}
                  </div>
                  <Textarea
                    readOnly
                    value={preview || '生成中...'}
                    className="resize-y font-mono text-xs"
                    rows={12}
                  />
                </div>
              )
            )}
          </>
        )}
      </div>
    </div>
  )
}
