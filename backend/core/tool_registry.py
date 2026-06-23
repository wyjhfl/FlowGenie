"""内置工具库 - 覆盖 8 大场景的常用工具"""
from typing import Any


class Tool:
    """工具定义"""
    def __init__(
        self,
        name: str,
        display_name: str,
        category: str,
        description: str,
        params_schema: dict,
        icon: str = "🔧",
        color: str = "#38bdf8",
    ):
        self.name = name
        self.display_name = display_name
        self.category = category
        self.description = description
        self.params_schema = params_schema
        self.icon = icon
        self.color = color

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "params_schema": self.params_schema,
            "icon": self.icon,
            "color": self.color,
        }


# 工具库注册表
TOOL_REGISTRY: list[Tool] = [
    # ===== 触发类 =====
    Tool(
        name="schedule_trigger",
        display_name="定时触发",
        category="触发",
        description="按时间计划触发工作流（cron 表达式或固定间隔）",
        params_schema={
            "cron": "0 8 * * *",
            "timezone": "Asia/Shanghai",
        },
        icon="⏰",
        color="#f59e0b",
    ),
    Tool(
        name="manual_trigger",
        display_name="手动触发",
        category="触发",
        description="用户手动点击按钮触发工作流",
        params_schema={},
        icon="👆",
        color="#f59e0b",
    ),
    Tool(
        name="webhook_trigger",
        display_name="Webhook 触发",
        category="触发",
        description="通过 HTTP Webhook 接收外部事件触发",
        params_schema={
            "path": "/webhook/custom",
            "method": "POST",
        },
        icon="🔗",
        color="#f59e0b",
    ),

    # ===== 数据获取类 =====
    Tool(
        name="http_request",
        display_name="HTTP 请求",
        category="数据获取",
        description="发起 HTTP/HTTPS 请求获取数据",
        params_schema={
            "url": "https://api.example.com/data",
            "method": "GET",
            "headers": {},
        },
        icon="🌐",
        color="#38bdf8",
    ),
    Tool(
        name="web_scraper",
        display_name="网页抓取",
        category="数据获取",
        description="抓取指定 URL 的网页内容，支持 CSS 选择器提取",
        params_schema={
            "url": "https://news.example.com",
            "selector": "article",
            "fields": ["title", "content"],
        },
        icon="🕷️",
        color="#38bdf8",
    ),
    Tool(
        name="rss_reader",
        display_name="RSS 订阅",
        category="数据获取",
        description="读取 RSS/Atom 订阅源获取最新文章",
        params_schema={
            "feed_url": "https://feeds.example.com/rss",
            "limit": 10,
        },
        icon="📡",
        color="#38bdf8",
    ),
    Tool(
        name="database_query",
        display_name="数据库查询",
        category="数据获取",
        description="执行 SQL 查询从数据库获取数据",
        params_schema={
            "connection": "postgresql://user:pass@host:5432/db",
            "query": "SELECT * FROM sales WHERE date >= $1",
        },
        icon="🗄️",
        color="#38bdf8",
    ),
    Tool(
        name="github_api",
        display_name="GitHub API",
        category="数据获取",
        description="调用 GitHub API 获取仓库、提交、Issue 等信息",
        params_schema={
            "endpoint": "/repos/{owner}/{repo}/commits",
            "owner": "owner",
            "repo": "repo",
        },
        icon="🐙",
        color="#38bdf8",
    ),

    # ===== AI 处理类 =====
    Tool(
        name="llm_summary",
        display_name="LLM 摘要",
        category="AI 处理",
        description="调用大语言模型生成文本摘要",
        params_schema={
            "model": "deepseek-chat",
            "max_length": 500,
            "language": "zh",
        },
        icon="🧠",
        color="#a78bfa",
    ),
    Tool(
        name="llm_analysis",
        display_name="LLM 分析",
        category="AI 处理",
        description="调用大语言模型进行数据分析、情感分析、内容审核等",
        params_schema={
            "model": "deepseek-chat",
            "task": "分析数据趋势并给出洞察",
        },
        icon="🧠",
        color="#a78bfa",
    ),
    Tool(
        name="llm_review",
        display_name="LLM Code Review",
        category="AI 处理",
        description="调用大语言模型对代码进行 Review，发现问题并给出建议",
        params_schema={
            "model": "deepseek-chat",
            "focus": ["bug", "security", "performance", "style"],
        },
        icon="🧠",
        color="#a78bfa",
    ),
    Tool(
        name="llm_generate",
        display_name="LLM 内容生成",
        category="AI 处理",
        description="调用大语言模型生成文案、报告、邮件等内容",
        params_schema={
            "model": "deepseek-chat",
            "content_type": "report",
            "tone": "professional",
        },
        icon="✍️",
        color="#a78bfa",
    ),

    # ===== 数据处理类 =====
    Tool(
        name="data_cleaner",
        display_name="数据清洗",
        category="数据处理",
        description="清洗数据：去重、填充空值、格式转换",
        params_schema={
            "rules": ["deduplicate", "trim_whitespace", "fill_null"],
        },
        icon="🧹",
        color="#10b981",
    ),
    Tool(
        name="chart_generator",
        display_name="图表生成",
        category="数据处理",
        description="根据数据生成可视化图表（柱状图/折线图/饼图）",
        params_schema={
            "type": "bar",
            "title": "数据报表",
            "x_field": "date",
            "y_field": "value",
        },
        icon="📊",
        color="#10b981",
    ),
    Tool(
        name="report_generator",
        display_name="报表生成",
        category="数据处理",
        description="将数据整理为结构化报表（支持 Markdown/HTML/PDF）",
        params_schema={
            "format": "html",
            "template": "default",
        },
        icon="📄",
        color="#10b981",
    ),

    # ===== 输出推送类 =====
    Tool(
        name="send_email",
        display_name="发送邮件",
        category="输出推送",
        description="通过 SMTP 发送邮件，支持 HTML 内容",
        params_schema={
            "to": "team@example.com",
            "subject": "工作流执行结果",
            "smtp_host": "smtp.example.com",
        },
        icon="📧",
        color="#ef4444",
    ),
    Tool(
        name="send_slack",
        display_name="Slack 推送",
        category="输出推送",
        description="向 Slack 频道发送消息",
        params_schema={
            "webhook_url": "https://hooks.slack.com/services/xxx",
            "channel": "#general",
        },
        icon="💬",
        color="#ef4444",
    ),
    Tool(
        name="send_wechat",
        display_name="微信推送",
        category="输出推送",
        description="通过企业微信机器人或公众号推送消息",
        params_schema={
            "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=xxx",
            "msg_type": "markdown",
        },
        icon="💚",
        color="#ef4444",
    ),
    Tool(
        name="send_dingtalk",
        display_name="钉钉推送",
        category="输出推送",
        description="通过钉钉机器人推送消息",
        params_schema={
            "webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=xxx",
        },
        icon="💙",
        color="#ef4444",
    ),
    Tool(
        name="file_write",
        display_name="文件写入",
        category="输出推送",
        description="将结果写入文件（本地或对象存储）",
        params_schema={
            "path": "/output/result.json",
            "format": "json",
        },
        icon="💾",
        color="#ef4444",
    ),
]


def get_all_tools() -> list[dict]:
    """获取所有工具的字典列表"""
    return [t.to_dict() for t in TOOL_REGISTRY]


def get_tool(name: str) -> Tool | None:
    """按 name 获取工具"""
    for t in TOOL_REGISTRY:
        if t.name == name:
            return t
    return None


def get_tools_description() -> str:
    """生成工具描述文本（供 Prompt 使用）"""
    lines = []
    for t in TOOL_REGISTRY:
        lines.append(f"- {t.name}: {t.description}")
    return "\n".join(lines)


def get_tools_by_category() -> dict[str, list[dict]]:
    """按分类获取工具"""
    result: dict[str, list[dict]] = {}
    for t in TOOL_REGISTRY:
        result.setdefault(t.category, []).append(t.to_dict())
    return result
