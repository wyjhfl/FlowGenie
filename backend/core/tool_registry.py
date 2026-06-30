"""内置工具库 - 覆盖 8 大场景的常用工具"""
import json
from functools import lru_cache
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
        required: list[str] = None,
        icon: str = "🔧",
        color: str = "#38bdf8",
        output_schema: dict = None,
    ):
        self.name = name
        self.display_name = display_name
        self.category = category
        self.description = description
        self.params_schema = params_schema
        self.required = required if required is not None else []
        self.icon = icon
        self.color = color
        self.output_schema = output_schema if output_schema is not None else {}

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "category": self.category,
            "description": self.description,
            "params_schema": self.params_schema,
            "required": self.required,
            "icon": self.icon,
            "color": self.color,
            "output_schema": self.output_schema,
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
        required=[],
        icon="⏰",
        color="#f59e0b",
        output_schema={"message": "str"},
    ),
    Tool(
        name="manual_trigger",
        display_name="手动触发",
        category="触发",
        description="用户手动点击按钮触发工作流",
        params_schema={},
        required=[],
        icon="👆",
        color="#f59e0b",
        output_schema={"message": "str"},
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
        required=[],
        icon="🔗",
        color="#f59e0b",
        output_schema={"message": "str"},
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
        required=["url", "method"],
        icon="🌐",
        color="#38bdf8",
        output_schema={"status_code": "int", "headers": "dict", "body": "any"},
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
        required=["url"],
        icon="🕷️",
        color="#38bdf8",
        output_schema={"title": "str", "url": "str", "items": "list[dict]", "count": "int", "page_text": "str", "warning": "str"},
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
        required=["feed_url"],
        icon="📡",
        color="#38bdf8",
        output_schema={"items": "list[dict]", "count": "int"},
    ),
    Tool(
        name="database_query",
        display_name="数据库查询",
        category="数据获取",
        description="执行 SQL 查询从数据库获取数据(仅 SELECT/WITH;支持 :param 参数化绑定)",
        params_schema={
            "query": "SELECT * FROM sales WHERE date >= :start_date",
            "params": {"start_date": "2026-01-01"},
        },
        required=["query"],
        icon="🗄️",
        color="#38bdf8",
        output_schema={"rows": "list[dict]", "count": "int", "columns": "list[str]", "message": "str"},
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
            "method": "GET",
            "params": {},
            "token": "",
        },
        required=["endpoint"],
        icon="🐙",
        color="#38bdf8",
        output_schema={"status_code": "int", "body": "any", "rate_limit_remaining": "int"},
    ),

    # ===== AI 处理类 =====
    Tool(
        name="llm_summary",
        display_name="LLM 摘要",
        category="AI 处理",
        description="调用大语言模型生成文本摘要",
        params_schema={
            "text": "待摘要的文本内容（可用 {{step_id.field}} 引用上一步输出）",
            "max_length": 500,
            "language": "zh",
        },
        required=["text"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"summary": "str", "original_length": "int"},
    ),
    Tool(
        name="llm_analysis",
        display_name="LLM 分析",
        category="AI 处理",
        description="调用大语言模型进行数据分析、情感分析、内容审核等",
        params_schema={
            "data": "待分析的数据（可用 {{step_id.field}} 引用上一步输出）",
            "task": "分析数据趋势并给出洞察",
        },
        required=["data"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"analysis": "str"},
    ),
    Tool(
        name="llm_review",
        display_name="LLM Code Review",
        category="AI 处理",
        description="调用大语言模型对代码进行 Review，发现问题并给出建议",
        params_schema={
            "code": "待审查的代码（可用 {{step_id.field}} 引用上一步输出）",
            "focus": ["bug", "security", "performance", "style"],
        },
        required=["code"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"review": "str", "issues_count": "int"},
    ),
    Tool(
        name="llm_generate",
        display_name="LLM 内容生成",
        category="AI 处理",
        description="调用大语言模型生成文案、报告、邮件等内容",
        params_schema={
            "content_type": "report",
            "topic": "生成主题（可用 {{step_id.field}} 引用上一步输出）",
            "tone": "professional",
            "language": "zh",
            "length": "",
        },
        required=["content_type", "topic"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"content": "str", "content_type": "str"},
    ),
    Tool(
        name="llm_translate",
        display_name="LLM 翻译",
        category="AI 处理",
        description="调用大语言模型进行多语言翻译",
        params_schema={
            "text": "待翻译文本(可用 {{step_id.field}} 引用上一步输出)",
            "source_lang": "auto",
            "target_lang": "en",
        },
        required=["text", "target_lang"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"translation": "str", "source_lang": "str", "target_lang": "str", "original_length": "int"},
    ),
    Tool(
        name="llm_classify",
        display_name="LLM 分类",
        category="AI 处理",
        description="调用大语言模型进行文本分类、情感分析、意图识别",
        params_schema={
            "text": "待分类文本(可用 {{step_id.field}} 引用上一步输出)",
            "categories": "类别列表,逗号分隔(可选,缺省按 task 给默认类)",
            "task": "sentiment",
        },
        required=["text"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"category": "str", "confidence": "float", "all_scores": "dict", "reason": "str"},
    ),
    Tool(
        name="llm_extract",
        display_name="LLM 信息抽取",
        category="AI 处理",
        description="调用大语言模型从文本中抽取结构化信息(实体/字段)",
        params_schema={
            "text": "待抽取文本(可用 {{step_id.field}} 引用上一步输出)",
            "schema": "name,age,email",
            "instruction": "补充说明(可选)",
        },
        required=["text", "schema"],
        icon="🧠",
        color="#a78bfa",
        output_schema={"entities": "dict", "count": "int", "raw": "str"},
    ),

    # ===== 数据处理类 =====
    Tool(
        name="file_read",
        display_name="文件读取",
        category="数据处理",
        description="读取本地文件内容，支持 text/json 格式",
        params_schema={
            "path": "/input/data.json",
            "format": "text",
        },
        required=["path"],
        icon="📄",
        color="#f59e0b",
        output_schema={"content": "any", "size": "int", "path": "str"},
    ),
    Tool(
        name="data_transform",
        display_name="数据转换",
        category="数据处理",
        description="数据转换：去重、字段映射、类型转换、条件过滤",
        params_schema={
            "data": "待处理的数据（可用 {{step_id.field}} 引用上一步输出）",
            "operations": [{"type": "deduplicate", "key": "id"}],
        },
        required=["data", "operations"],
        icon="🔄",
        color="#f59e0b",
        output_schema={"data": "any", "count": "int"},
    ),
    Tool(
        name="chart_generator",
        display_name="图表生成",
        category="数据处理",
        description="根据数据生成可视化图表（HTML 表格/ASCII 柱状图/ASCII 饼图）",
        params_schema={
            "data": "待可视化的数据（可用 {{step_id.field}} 引用上一步输出）",
            "chart_type": "table",
            "title": "数据报表",
            "x_field": "date",
            "y_field": "value",
        },
        required=["data", "chart_type"],
        icon="📊",
        color="#f59e0b",
        output_schema={"chart_html": "str", "chart_type": "str", "data_points": "int"},
    ),
    Tool(
        name="code_node",
        display_name="代码执行",
        category="数据处理",
        description="执行 Python 代码处理自定义数据逻辑",
        params_schema={
            "code": "Python代码（可用input变量访问输入数据，用result=设置输出）",
            "input": "输入数据（可用{{step_id.field}}引用）",
        },
        required=["code"],
        icon="🐍",
        color="#f59e0b",
        output_schema={"result": "any", "success": "bool", "error": "str"},
    ),
    Tool(
        name="text_template",
        display_name="文本模板",
        category="数据处理",
        description="用 {{var}} 占位符渲染文本模板,支持多步结果拼接",
        params_schema={
            "template": "今天是 {{date}},报告: {{report}}",
            "variables": {"date": "2026-01-01", "report": "可用 {{step_id.field}} 引用"},
        },
        required=["template"],
        icon="📝",
        color="#f59e0b",
        output_schema={"rendered": "str", "length": "int"},
    ),

    # ===== 数据处理扩展(低代码数据处理,降低 code_node 滥用) =====
    Tool(
        name="json_path",
        display_name="JSON路径提取",
        category="数据处理",
        description="用简化 JSONPath 从 JSON 中提取值,支持 $.a.b / $.a[*].c / $.a[0]",
        params_schema={
            "data": "JSON 数据(可用 {{step_id.field}} 引用)",
            "path": "$.a.b",
        },
        required=["data", "path"],
        icon="🔍",
        color="#f59e0b",
        output_schema={"values": "list", "count": "int"},
    ),
    Tool(
        name="regex_extract",
        display_name="正则提取",
        category="数据处理",
        description="用正则表达式从文本中提取匹配内容",
        params_schema={
            "text": "待匹配文本(可用 {{step_id.field}} 引用)",
            "pattern": r"\d+",
            "group": 0,
        },
        required=["text", "pattern"],
        icon="🔎",
        color="#f59e0b",
        output_schema={"matches": "list[str]", "count": "int"},
    ),
    Tool(
        name="date_format",
        display_name="日期格式化",
        category="数据处理",
        description="日期格式化/时区转换/日期运算(加减天数)",
        params_schema={
            "datetime": "输入时间(空则用 now)",
            "input_format": "%Y-%m-%d",
            "output_format": "%Y-%m-%d %H:%M:%S",
            "timezone": "Asia/Shanghai",
            "add_days": 0,
        },
        required=[],
        icon="📅",
        color="#f59e0b",
        output_schema={"formatted": "str", "timestamp": "int", "iso": "str"},
    ),
    Tool(
        name="array_ops",
        display_name="数组操作",
        category="数据处理",
        description="数组操作:排序/切片/展平/去重/抽样",
        params_schema={
            "array": "[1, 2, 3] 或对象数组(可用 {{step_id.field}} 引用)",
            "operation": "sort",
            "key": "id",
            "start": 0,
            "end": 10,
            "count": 1,
        },
        required=["array", "operation"],
        icon="📊",
        color="#f59e0b",
        output_schema={"result": "list", "count": "int"},
    ),
    Tool(
        name="math_calculate",
        display_name="数学计算",
        category="数据处理",
        description="数学聚合:求和/均值/最值/计数/四舍五入",
        params_schema={
            "data": "[1, 2, 3] 或对象数组(可用 {{step_id.field}} 引用)",
            "operation": "sum",
            "field": "value",
            "precision": 2,
        },
        required=["data", "operation"],
        icon="🧮",
        color="#f59e0b",
        output_schema={"result": "number", "operation": "str"},
    ),

    # ===== 输出推送类 =====
    Tool(
        name="send_email",
        display_name="发送邮件",
        category="输出推送",
        description="通过 SMTP 发送邮件（SMTP 配置从 .env 读取），支持 plain/html",
        params_schema={
            "to": "recipient@example.com",
            "subject": "工作流执行结果",
            "content": "邮件正文（可用 {{step_id.field}} 引用上一步输出）",
            "content_type": "plain",
        },
        required=["to", "subject", "content"],
        icon="📧",
        color="#ef4444",
        output_schema={"success": "bool", "message": "str"},
    ),
    Tool(
        name="send_slack",
        display_name="Slack 推送",
        category="输出推送",
        description="向 Slack 频道发送消息（Webhook URL 从 .env 或参数读取）",
        params_schema={
            "text": "要发送的消息内容（可用 {{step_id.field}} 引用上一步输出）",
        },
        required=["text"],
        icon="💬",
        color="#ef4444",
        output_schema={"success": "bool", "response": "str"},
    ),
    Tool(
        name="send_wechat",
        display_name="微信推送",
        category="输出推送",
        description="通过企业微信机器人推送消息（Webhook URL 从 .env 或参数读取）",
        params_schema={
            "content": "要发送的内容（可用 {{step_id.field}} 引用上一步输出）",
            "msg_type": "markdown",
        },
        required=["content"],
        icon="💚",
        color="#ef4444",
        output_schema={"success": "bool", "response": "dict"},
    ),
    Tool(
        name="send_dingtalk",
        display_name="钉钉推送",
        category="输出推送",
        description="通过钉钉机器人推送消息（Webhook URL 从 .env 或参数读取）",
        params_schema={
            "content": "要发送的内容（可用 {{step_id.field}} 引用上一步输出）",
            "msg_type": "text",
            "at_mobiles": [],
        },
        required=["content"],
        icon="🔔",
        color="#ef4444",
        output_schema={"success": "bool", "response": "dict"},
    ),
    Tool(
        name="send_telegram",
        display_name="Telegram 推送",
        category="输出推送",
        description="通过 Telegram Bot 推送消息到指定聊天（Bot Token 从 .env TELEGRAM_BOT_TOKEN 读取）",
        params_schema={
            "chat_id": "目标聊天 ID",
            "text": "要发送的消息内容（可用 {{step_id.field}} 引用上一步输出）",
            "parse_mode": "text",
        },
        required=["chat_id", "text"],
        icon="✈️",
        color="#0088cc",
        output_schema={"message_id": "int", "chat_id": "str", "date": "int"},
    ),
    Tool(
        name="file_write",
        display_name="文件写入",
        category="输出推送",
        description="将结果写入文件（本地或对象存储）",
        params_schema={
            "path": "/output/result.json",
            "format": "json",
            "content": "写入内容（可用 {{step_id.field}} 引用）",
        },
        required=["path", "content"],
        icon="💾",
        color="#ef4444",
        output_schema={"success": "bool", "path": "str", "size": "int"},
    ),
    Tool(
        name="notion_api",
        display_name="Notion 写入",
        category="输出推送",
        description="将数据写入 Notion 数据库(token 从 .env NOTION_TOKEN 读取或参数传入)",
        params_schema={
            "database_id": "Notion 数据库 ID",
            "properties": {"字段名": "值"},
            "token": "",
        },
        required=["database_id", "properties"],
        icon="📓",
        color="#ef4444",
        output_schema={"success": "bool", "page_id": "str", "url": "str", "message": "str"},
    ),
    Tool(
        name="feishu_api",
        display_name="飞书推送",
        category="输出推送",
        description="通过飞书机器人 webhook 推送消息(webhook URL 从 .env FEISHU_WEBHOOK_URL 读取或参数传入)",
        params_schema={
            "content": "消息内容(可用 {{step_id.field}} 引用上一步输出)",
            "msg_type": "text",
            "webhook_url": "",
        },
        required=["content"],
        icon="🐦",
        color="#ef4444",
        output_schema={"success": "bool", "response": "dict", "message": "str"},
    ),

    # ===== 智能体类 =====
    Tool(
        name="function_call",
        display_name="Function Calling 智能体",
        category="AI 处理",
        description="F1: LLM 自主决策调用工具并循环推理,直到给出最终答案(Agent 模式)。选择可用工具后,LLM 会自动决定调用哪些工具、传入什么参数,并根据工具结果继续推理",
        params_schema={
            "prompt": "要解决的问题或任务描述(可用 {{step_id.field}} 引用上一步输出)",
            "tools": ["http_request", "web_scraper", "llm_summary"],
            "max_iterations": 10,
            "model": "",
        },
        required=["prompt", "tools"],
        icon="🤖",
        color="#a78bfa",
        output_schema={"answer": "str", "iterations": "int", "tool_calls_history": "list", "warning": "str"},
    ),

    # ===== F2: 会话记忆类 =====
    Tool(
        name="conversation_start",
        display_name="创建会话",
        category="AI 处理",
        description="F2: 创建一个多轮对话会话,设定系统提示词。返回 session_id 供后续 conversation_continue/list 使用。会话默认 7 天过期,每次续聊自动续期",
        params_schema={
            "system_prompt": "会话的系统提示词(定义助手角色/行为,如:你是一位客服助手)",
            "session_id": "业务会话 ID(可选,缺省自动生成;指定后可用该 ID 跨执行续聊)",
            "model": "模型名(可选,空则用默认模型)",
        },
        required=["system_prompt"],
        icon="💬",
        color="#a78bfa",
        output_schema={"session_id": "str", "message_count": "int", "created_at": "str", "expires_at": "str", "warning": "str"},
    ),
    Tool(
        name="conversation_continue",
        display_name="续聊会话",
        category="AI 处理",
        description="F2: 向已有会话追加用户消息并获取 LLM 回复(自动加载历史消息保持上下文)。每次调用续期 7 天过期。需先用 conversation_start 创建会话",
        params_schema={
            "session_id": "会话 ID(由 conversation_start 返回,可用 {{step_id.session_id}} 引用)",
            "user_message": "用户本轮消息(可用 {{step_id.field}} 引用上一步输出)",
            "model": "模型名(可选,覆盖会话创建时的模型)",
            "temperature": 0.3,
            "max_tokens": 2000,
        },
        required=["session_id", "user_message"],
        icon="💬",
        color="#a78bfa",
        output_schema={"reply": "str", "session_id": "str", "message_count": "int", "warning": "str"},
    ),
    Tool(
        name="conversation_list",
        display_name="查看会话历史",
        category="AI 处理",
        description="F2: 查看指定会话的全部历史消息(不调用 LLM,仅读取)。用于调试、导出对话记录",
        params_schema={
            "session_id": "会话 ID",
        },
        required=["session_id"],
        icon="💬",
        color="#a78bfa",
        output_schema={"session_id": "str", "messages": "list", "message_count": "int", "system_prompt": "str", "updated_at": "str", "warning": "str"},
    ),

    # ===== 逻辑控制类 =====
    Tool(
        name="if_else",
        display_name="条件分支",
        category="逻辑控制",
        description="根据条件判断选择执行路径，edges 需标记 condition 为 true 或 false",
        params_schema={
            "field": "要判断的字段值（可用 {{step_id.field}} 引用上一步输出）",
            "operator": "eq/ne/gt/ge/lt/le/is_empty/is_not_empty/is_null/is_not_null/contain/not_contain/len_gt/len_ge/len_lt/len_le/startwith/endwith",
            "value": "比较的目标值",
        },
        required=["field", "operator"],
        icon="🔀",
        color="#fbbf24",
        output_schema={"result": "bool", "branch": "str"},
    ),
    Tool(
        name="loop",
        display_name="循环遍历",
        category="逻辑控制",
        description="对数组类型的数据遍历执行子流程，子流程步骤定义在 sub_steps 中。支持 break_on 提前终止和 max_iterations 限制迭代数",
        params_schema={
            "input_array": "要遍历的数组（可用 {{step_id.field}} 引用上一步输出的数组）",
            "sub_steps": [{"id": "sub_1", "name": "处理单项", "tool": "llm_summary", "params": {"text": "{{item}}"}}],
            "sub_edges": [],
            "break_on": "可选,提前终止条件: 'success'(子流程成功即停) 或 'failed'(子流程失败即停),不填则遍历全部",
            "max_iterations": "可选,最大迭代数(不超过 input_array 长度),用于只处理前 N 项",
        },
        required=["input_array", "sub_steps"],
        icon="🔁",
        color="#fbbf24",
        output_schema={"results": "list", "count": "int", "broken": "bool 是否提前终止"},
    ),
    Tool(
        name="wait_delay",
        display_name="延时等待",
        category="逻辑控制",
        description="暂停工作流执行指定时长(seconds/minutes/hours)",
        params_schema={
            "duration": 10,
            "unit": "seconds",
        },
        required=["duration"],
        icon="⏳",
        color="#fbbf24",
        output_schema={"waited_seconds": "int", "message": "str"},
    ),
    Tool(
        name="switch_branch",
        display_name="多路分支",
        category="逻辑控制",
        description="按字段值路由到不同分支,edges 需标记 case 标签,未命中走 default",
        params_schema={
            "field": "要判断的字段值(可用 {{step_id.field}} 引用)",
            "cases": ["case_a", "case_b"],
        },
        required=["field", "cases"],
        icon="🔀",
        color="#fbbf24",
        output_schema={"matched_case": "str", "branch": "str"},
    ),
    # A1: 人工审批节点——执行到此节点时暂停工作流,等待人工批准/拒绝后恢复
    Tool(
        name="approve_node",
        display_name="人工审批",
        category="逻辑控制",
        description="A1: 执行到此节点时暂停工作流,等待人工批准/拒绝后恢复。超时(默认24h)自动拒绝。批准继续执行后续步骤,拒绝标记失败",
        params_schema={
            "message": "审批说明(描述需要审批的内容,如\"金额>1万的订单需主管审批\")",
            "approvers": ["审批人列表(本轮仅记录,不强制鉴权)"],
            "timeout_hours": 24,
        },
        required=["message"],
        icon="✋",
        color="#ef4444",
        output_schema={"decision": "str", "comment": "str", "approved_by": "str"},
    ),
    # A2: 子流程调用——引用已保存的工作流作为子流程,递归执行并返回结果
    Tool(
        name="subworkflow",
        display_name="子流程调用",
        category="逻辑控制",
        description="A2: 调用另一个已保存的工作流作为子流程,实现工作流复用与嵌套。通过 workflow_id 指定目标工作流,input_mapping 传递参数。嵌套深度上限 5 层,自动检测循环引用",
        params_schema={
            "workflow_id": "要调用的目标工作流 ID(在节点配置面板下拉选择)",
            "input_mapping": {"key": "value 可用 {{step_id.field}} 引用父流程数据,作为子流程的 trigger_data"},
        },
        required=["workflow_id"],
        icon="📦",
        color="#fbbf24",
        output_schema={"status": "str 子流程执行状态", "output": "any 子流程末步输出", "sub_steps_result": "dict 子流程全部步骤结果"},
    ),

    # ===== C1: 对象存储(S3 兼容) =====
    Tool(
        name="object_storage_upload",
        display_name="对象存储-上传",
        category="数据存储",
        description="C1: 上传文件到 S3 兼容对象存储(MinIO/Ceph/AWS S3)。需先在凭证面板配置 S3_ENDPOINT_URL/S3_ACCESS_KEY/S3_SECRET_KEY/S3_BUCKET",
        params_schema={
            "key": "对象 key(S3 路径,如 reports/2026/report.json;前导 / 会自动去除)",
            "content": "上传内容(可用 {{step_id.field}} 引用上一步输出;支持字符串/字典/列表)",
            "content_type": "application/json",
        },
        required=["key", "content"],
        icon="☁️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "bucket": "str", "key": "str", "size": "int", "endpoint": "str", "warning": "str"},
    ),
    Tool(
        name="object_storage_download",
        display_name="对象存储-下载",
        category="数据存储",
        description="C1: 从 S3 兼容对象存储下载文件内容。encoding 为 utf-8 返回文本,为 binary 返回 base64 编码",
        params_schema={
            "key": "对象 key(可用 {{step_id.field}} 引用上一步输出)",
            "encoding": "utf-8",
        },
        required=["key"],
        icon="☁️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "bucket": "str", "key": "str", "size": "int", "content": "str", "encoding": "str", "warning": "str"},
    ),
    Tool(
        name="object_storage_delete",
        display_name="对象存储-删除",
        category="数据存储",
        description="C1: 删除 S3 兼容对象存储上的 object",
        params_schema={
            "key": "对象 key(可用 {{step_id.field}} 引用上一步输出)",
        },
        required=["key"],
        icon="☁️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "bucket": "str", "key": "str", "warning": "str"},
    ),
    Tool(
        name="object_storage_list",
        display_name="对象存储-列举",
        category="数据存储",
        description="C1: 列举 S3 兼容对象存储 bucket 下的 object,支持按 prefix 过滤",
        params_schema={
            "prefix": "对象 key 前缀过滤(可选,如 reports/2026/)",
            "limit": 100,
        },
        required=[],
        icon="☁️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "bucket": "str", "prefix": "str", "items": "list[dict]", "count": "int", "is_truncated": "bool", "warning": "str"},
    ),

    # ===== C2: PDF 生成 =====
    Tool(
        name="pdf_generator",
        display_name="PDF 生成",
        category="数据存储",
        description="C2: 使用 reportlab 生成 PDF 文档,支持 text(纯文本段落)和 table(表格,首行表头)两种模式。输出到工作区文件,返回路径与文件大小",
        params_schema={
            "path": "输出 PDF 路径(工作区内,如 reports/2026.pdf)",
            "title": "文档标题(可选)",
            "mode": "text",
            "text": "mode=text 时的正文内容(可用 {{step_id.field}} 引用上一步输出;支持换行)",
            "rows": [["姓名", "分数"], ["张三", 90], ["李四", 85]],
        },
        required=["path", "mode"],
        icon="📄",
        color="#10b981",
        output_schema={"success": "bool", "path": "str", "size": "int", "title": "str", "mode": "str", "rows_count": "int", "warning": "str"},
    ),

    # ===== C3: Excel 读写 =====
    Tool(
        name="excel_write",
        display_name="Excel 写入",
        category="数据存储",
        description="C3: 将二维数组写入 .xlsx 文件(首行作为表头加粗),自动调整列宽。输出到工作区,返回路径/大小/行列数",
        params_schema={
            "path": "输出 xlsx 路径(工作区内,如 reports/data.xlsx)",
            "rows": [["姓名", "分数"], ["张三", 90]],
            "sheet_name": "Sheet1",
        },
        required=["path", "rows"],
        icon="📊",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "path": "str", "size": "int", "sheet_name": "str", "rows_written": "int", "cols_written": "int", "warning": "str"},
    ),
    Tool(
        name="excel_read",
        display_name="Excel 读取",
        category="数据存储",
        description="C3: 读取 .xlsx 文件内容,返回二维数组。支持指定 sheet、是否有表头、行数限制",
        params_schema={
            "path": "输入 xlsx 路径(工作区内)",
            "sheet_name": "Sheet 名(可选,空则用 active sheet)",
            "has_header": True,
            "limit": 0,
        },
        required=["path"],
        icon="📊",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "path": "str", "sheet_name": "str", "header": "list", "rows": "list[list]", "rows_count": "int", "total_rows": "int", "warning": "str"},
    ),

    # ===== C4: 图像处理 =====
    Tool(
        name="image_resize",
        display_name="图像-调整尺寸",
        category="数据存储",
        description="C4: 调整图像尺寸,支持保持比例。使用 LANCZOS 高质量重采样。输入/输出在工作区内",
        params_schema={
            "input_path": "输入图像路径(工作区内,如 photos/orig.png)",
            "output_path": "输出图像路径(工作区内,如 photos/resized.png)",
            "width": 800,
            "height": 600,
            "keep_ratio": True,
        },
        required=["input_path", "output_path", "width", "height"],
        icon="🖼️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "input_path": "str", "output_path": "str", "original_size": "list", "new_size": "list", "keep_ratio": "bool", "size": "int", "warning": "str"},
    ),
    Tool(
        name="image_convert",
        display_name="图像-格式转换",
        category="数据存储",
        description="C4: 转换图像格式(jpg/png/webp/gif/bmp)。JPEG 自动处理 alpha 通道转 RGB,可指定质量",
        params_schema={
            "input_path": "输入图像路径",
            "output_path": "输出图像路径(扩展名决定格式)",
            "target_format": "JPEG",
            "quality": 85,
        },
        required=["input_path", "output_path", "target_format"],
        icon="🖼️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "input_path": "str", "output_path": "str", "original_format": "str", "new_format": "str", "quality": "int", "size": "int", "warning": "str"},
    ),
    Tool(
        name="image_thumbnail",
        display_name="图像-缩略图",
        category="数据存储",
        description="C4: 生成缩略图(保持比例,max_size 为最长边的最大像素)",
        params_schema={
            "input_path": "输入图像路径",
            "output_path": "输出缩略图路径",
            "max_size": 200,
        },
        required=["input_path", "output_path"],
        icon="🖼️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "input_path": "str", "output_path": "str", "original_size": "list", "new_size": "list", "max_size": "int", "size": "int", "warning": "str"},
    ),
    Tool(
        name="image_info",
        display_name="图像-信息",
        category="数据存储",
        description="C4: 读取图像元信息(格式/色彩模式/宽高/文件大小)",
        params_schema={
            "input_path": "输入图像路径",
        },
        required=["input_path"],
        icon="🖼️",
        color="#10b981",
        output_schema={"success": "bool", "operation": "str", "path": "str", "format": "str", "mode": "str", "size": "list", "width": "int", "height": "int", "file_size": "int", "warning": "str"},
    ),

    # ===== C5: 向量检索/RAG =====
    Tool(
        name="embedding",
        display_name="文本向量化",
        category="AI 处理",
        description="C5: 调用 LLM 兼容 /v1/embeddings 接口将文本批量向量化,作为向量检索/RAG 基础。模型缺省用 env LLM_EMBEDDING_MODEL(text-embedding-3-small)",
        params_schema={
            "texts": ["待向量化的文本列表(最多 100 条,单条超 8000 字符自动截断)"],
            "model": "embedding 模型名(可选,空则用 env LLM_EMBEDDING_MODEL)",
        },
        required=["texts"],
        icon="🔢",
        color="#a78bfa",
        output_schema={"success": "bool", "vectors": "list[list[float]]", "dim": "int", "count": "int", "model": "str", "warning": "str"},
    ),
    Tool(
        name="vector_store_upsert",
        display_name="向量存储-写入",
        category="AI 处理",
        description="C5: 写入/更新向量记录到本地向量存储(pickle 文件)。items 每项可包含 vector(已有向量)或仅 text(自动调用 embedding)。同 id 覆盖",
        params_schema={
            "store_path": "向量存储文件路径(工作区内,如 vectors/kb.pkl)",
            "items": [{"id": "doc_1", "text": "文档内容", "vector": [0.1, 0.2], "metadata": {"source": "url"}}],
            "model": "embedding 模型名(可选,自动向量化时使用)",
        },
        required=["store_path", "items"],
        icon="🗃️",
        color="#a78bfa",
        output_schema={"success": "bool", "operation": "str", "store_path": "str", "count": "int", "dim": "int", "model": "str", "upserted": "int", "warning": "str"},
    ),
    Tool(
        name="vector_store_search",
        display_name="向量存储-检索",
        category="AI 处理",
        description="C5: 余弦相似度 Top-K 检索。query(文本,自动向量化)与 query_vector(向量)二选一,后者优先",
        params_schema={
            "store_path": "向量存储文件路径",
            "query": "文本查询(自动向量化)",
            "query_vector": [0.1, 0.2],
            "top_k": 5,
            "model": "embedding 模型名(可选,文本查询时使用)",
        },
        required=["store_path"],
        icon="🔎",
        color="#a78bfa",
        output_schema={"success": "bool", "operation": "str", "store_path": "str", "results": "list[dict]", "count": "int", "top_k": "int", "store_count": "int", "warning": "str"},
    ),
    Tool(
        name="vector_store_delete",
        display_name="向量存储-删除",
        category="AI 处理",
        description="C5: 按 id 列表批量删除向量记录",
        params_schema={
            "store_path": "向量存储文件路径",
            "ids": ["doc_1", "doc_2"],
        },
        required=["store_path", "ids"],
        icon="🗑️",
        color="#a78bfa",
        output_schema={"success": "bool", "operation": "str", "store_path": "str", "deleted": "int", "remaining": "int", "warning": "str"},
    ),
]


# 工具名/显示名 -> Tool 的 dict 索引(模块加载时构建,O(1) 查询)
_TOOL_INDEX: dict[str, Tool] = {t.name: t for t in TOOL_REGISTRY}
_TOOL_DISPLAY_INDEX: dict[str, Tool] = {t.display_name: t for t in TOOL_REGISTRY}


@lru_cache(maxsize=1)
def get_all_tools() -> tuple[dict, ...]:
    """获取所有工具的字典列表(返回 tuple 以便 lru_cache 哈希,启动后不变)"""
    return tuple(t.to_dict() for t in TOOL_REGISTRY)


def get_tool(name: str) -> Tool | None:
    """按 name 获取工具(O(1) dict 索引)"""
    return _TOOL_INDEX.get(name)


def get_tool_by_display_name(display_name: str) -> Tool | None:
    """按 display_name 获取工具(O(1) dict 索引)"""
    return _TOOL_DISPLAY_INDEX.get(display_name)


def _format_example(value: Any) -> str:
    """格式化参数示例值：dict/list 用紧凑 JSON，其余用 str"""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


@lru_cache(maxsize=1)
def get_tools_description() -> str:
    """生成工具描述文本（供 Prompt 使用），包含 params_schema 与 required 信息"""
    lines = []
    for t in TOOL_REGISTRY:
        lines.append(f"- {t.name} [{t.display_name}]: {t.description}")
        param_parts = []
        for key, example in t.params_schema.items():
            required_tag = "必填, " if key in t.required else ""
            param_parts.append(f"{key}({required_tag}示例:{_format_example(example)})")
        if param_parts:
            lines.append("  参数: " + ", ".join(param_parts))
        else:
            lines.append("  参数: (无)")
        if t.required:
            lines.append(f"  必填: {', '.join(t.required)}")
        if t.output_schema:
            output_parts = [f"{k}: {v}" for k, v in t.output_schema.items()]
            lines.append("  输出: {" + ", ".join(output_parts) + "}")
    return "\n".join(lines)


def get_tools_by_category() -> dict[str, list[dict]]:
    """按分类获取工具"""
    result: dict[str, list[dict]] = {}
    for t in TOOL_REGISTRY:
        result.setdefault(t.category, []).append(t.to_dict())
    return result


def _infer_json_type(value: Any) -> str:
    """从示例值推断 JSON Schema 类型(供 get_tool_schema 使用)"""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return "string"


def get_tool_schema(name: str) -> dict | None:
    """F1: 生成 OpenAI Function Calling 兼容的 tool schema(从 Tool.params_schema 转换)

    :param name: 工具名(如 http_request)
    :return: OpenAI tools 格式 dict,工具不存在返回 None
    """
    tool = get_tool(name)
    if tool is None:
        return None
    properties: dict[str, Any] = {}
    for key, example in tool.params_schema.items():
        properties[key] = {
            "type": _infer_json_type(example),
            "description": f"示例: {_format_example(example)}",
        }
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(tool.required),
            },
        },
    }


def get_tool_schemas(names: list[str]) -> list[dict]:
    """F1: 批量获取工具 schema(跳过不存在的工具)"""
    schemas: list[dict] = []
    for n in names:
        schema = get_tool_schema(n)
        if schema is not None:
            schemas.append(schema)
    return schemas
