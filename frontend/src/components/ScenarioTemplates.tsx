// 场景模板配置
import type { ScenarioTemplate } from '../types/workflow'

export const SCENARIO_TEMPLATES: ScenarioTemplate[] = [
  {
    key: 'news',
    title: '每日新闻摘要推送',
    description: '抓取新闻 → 生成摘要 → 推送微信',
    requirement: '每天早上8点抓取科技新闻生成摘要推送到微信',
    icon: '📰',
  },
  {
    key: 'sales',
    title: '销售数据报表生成',
    description: '查询数据 → 生成图表 → 邮件发送',
    requirement: '每周一从数据库导出销售数据生成可视化报表邮件发给团队',
    icon: '📈',
  },
  {
    key: 'review',
    title: '代码提交 Code Review',
    description: '获取提交 → AI Review → Slack 推送',
    requirement: '每次代码提交后自动进行code review把问题发到slack',
    icon: '🖥️',
  },
]
