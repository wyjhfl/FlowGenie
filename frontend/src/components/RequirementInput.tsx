// 自然语言需求输入框
import { useState } from 'react'
import { SCENARIO_TEMPLATES } from './ScenarioTemplates'

interface Props {
  onParse: (requirement: string) => void
  loading: boolean
}

export function RequirementInput({ onParse, loading }: Props) {
  const [value, setValue] = useState('')

  const handleSubmit = () => {
    if (value.trim() && !loading) {
      onParse(value.trim())
    }
  }

  const handleTemplate = (requirement: string) => {
    setValue(requirement)
    if (!loading) onParse(requirement)
  }

  return (
    <div className="input-panel">
      <h3>描述你的工作流需求</h3>
      <textarea
        className="requirement-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="例如：每天早上8点抓取科技新闻，生成摘要，发到我的微信"
        rows={4}
        disabled={loading}
      />
      <button
        className="btn btn-primary"
        onClick={handleSubmit}
        disabled={!value.trim() || loading}
      >
        {loading ? '生成中...' : '生成工作流'}
      </button>

      <div className="templates">
        <p className="templates-title">或试试这些场景模板：</p>
        <div className="template-grid">
          {SCENARIO_TEMPLATES.map((t) => (
            <button
              key={t.key}
              className="template-card"
              onClick={() => handleTemplate(t.requirement)}
              disabled={loading}
            >
              <span className="template-icon">{t.icon}</span>
              <span className="template-name">{t.title}</span>
              <span className="template-desc">{t.description}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
