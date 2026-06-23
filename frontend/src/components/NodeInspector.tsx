// 节点参数查看面板
import type { WorkflowStep } from '../types/workflow'

interface Props {
  step: WorkflowStep | null
}

export function NodeInspector({ step }: Props) {
  if (!step) {
    return (
      <div className="inspector">
        <h3>节点详情</h3>
        <p className="inspector-empty">点击节点查看参数详情</p>
      </div>
    )
  }

  const toolInfo = step.tool_info
  const params = step.params || {}

  return (
    <div className="inspector">
      <h3>节点详情</h3>
      <div className="inspector-section">
        <div className="inspector-row">
          <span className="label">步骤名称</span>
          <span className="value">{step.name}</span>
        </div>
        <div className="inspector-row">
          <span className="label">步骤说明</span>
          <span className="value">{step.description}</span>
        </div>
        <div className="inspector-row">
          <span className="label">使用工具</span>
          <span className="value">
            {toolInfo?.icon} {toolInfo?.display_name || step.tool}
          </span>
        </div>
        <div className="inspector-row">
          <span className="label">工具分类</span>
          <span className="value">{toolInfo?.category || '-'}</span>
        </div>
        <div className="inspector-row">
          <span className="label">工具说明</span>
          <span className="value">{toolInfo?.description || '-'}</span>
        </div>
      </div>

      <div className="inspector-section">
        <h4>参数配置</h4>
        {Object.keys(params).length === 0 ? (
          <p className="inspector-empty">该步骤无参数</p>
        ) : (
          <div className="params-list">
            {Object.entries(params).map(([key, val]) => (
              <div key={key} className="param-row">
                <span className="param-key">{key}</span>
                <span className="param-value">
                  {typeof val === 'object' ? JSON.stringify(val) : String(val)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
