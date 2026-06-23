// 导出面板
import { useState } from 'react'
import type { ParseResponse } from '../types/workflow'
import { exportWorkflow } from '../services/api'

interface Props {
  workflow: ParseResponse | null
}

export function ExportPanel({ workflow }: Props) {
  const [format, setFormat] = useState<'trae_skill' | 'trae_skill_yaml' | 'json'>('trae_skill')
  const [preview, setPreview] = useState<string>('')
  const [loading, setLoading] = useState(false)
  const [showPreview, setShowPreview] = useState(false)

  const handleExport = async () => {
    if (!workflow) return
    setLoading(true)
    setShowPreview(true)
    try {
      const result = await exportWorkflow(workflow, format)
      setPreview(result.content)
    } catch (e) {
      setPreview('导出失败：' + (e instanceof Error ? e.message : String(e)))
    } finally {
      setLoading(false)
    }
  }

  const handleDownload = () => {
    if (!preview) return
    const blob = new Blob([preview], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const ext = format === 'trae_skill' ? 'json' : format === 'trae_skill_yaml' ? 'yaml' : 'json'
    a.download = `flowgenie_workflow.${ext}`
    a.click()
    URL.revokeObjectURL(url)
  }

  const formatLabels: Record<string, string> = {
    trae_skill: 'TRAE Skill (JSON)',
    trae_skill_yaml: 'TRAE Skill (YAML)',
    json: '通用 JSON',
  }

  return (
    <div className="export-panel">
      <h3>导出工作流</h3>
      {!workflow ? (
        <p className="export-empty">请先生成工作流</p>
      ) : (
        <>
          <div className="export-info">
            <span className="badge badge-source">{workflow.source}</span>
            <span className="badge badge-scenario">{workflow.scenario}</span>
          </div>

          <div className="export-controls">
            <select
              className="format-select"
              value={format}
              onChange={(e) => setFormat(e.target.value as typeof format)}
            >
              {Object.entries(formatLabels).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
            <button className="btn btn-primary" onClick={handleExport} disabled={loading}>
              {loading ? '导出中...' : '生成导出'}
            </button>
            {preview && (
              <button className="btn btn-secondary" onClick={handleDownload}>
                下载文件
              </button>
            )}
          </div>

          {showPreview && (
            <div className="export-preview">
              <h4>预览</h4>
              <pre className="preview-code">{preview || '生成中...'}</pre>
            </div>
          )}
        </>
      )}
    </div>
  )
}
