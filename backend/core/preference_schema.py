"""用户偏好 schema 定义 - 统一管理偏好项的元信息

每项偏好含:
- key: 偏好键名(存 UserPreference.key)
- category: 分组类别(前端按此分组渲染)
- display_name: 显示名
- type: text | secret | number | boolean | select
- default: 默认值
- options: select 类型的可选值列表
- applicable_tools: {tool_name: [param_name, ...]} 可自动填充的工具参数映射
- description: 描述说明
"""
from typing import Any


PREFERENCE_ITEMS: list[dict[str, Any]] = [
    # ===== 联系方式 =====
    {
        "key": "email",
        "category": "联系方式",
        "display_name": "默认邮箱",
        "type": "text",
        "default": "",
        "options": None,
        "applicable_tools": {"send_email": ["to"]},
        "description": "发送邮件时的默认收件人",
    },
    # ===== IM 推送 =====
    {
        "key": "telegram_chat_id",
        "category": "IM推送",
        "display_name": "Telegram Chat ID",
        "type": "text",
        "default": "",
        "options": None,
        "applicable_tools": {"send_telegram": ["chat_id"]},
        "description": "Telegram 推送的默认会话 ID",
    },
    {
        "key": "slack_webhook_url",
        "category": "IM推送",
        "display_name": "Slack Webhook URL",
        "type": "secret",
        "default": "",
        "options": None,
        "applicable_tools": {"send_slack": ["webhook_url"]},
        "description": "Slack 推送的默认 Webhook URL",
    },
    # ===== AI 处理 =====
    {
        "key": "default_language",
        "category": "AI处理",
        "display_name": "默认语言",
        "type": "select",
        "default": "zh",
        "options": ["zh", "en"],
        "applicable_tools": {
            "llm_summary": ["language"],
            "llm_translate": ["target_lang"],
        },
        "description": "LLM 摘要/翻译的默认语言",
    },
    {
        "key": "default_summary_length",
        "category": "AI处理",
        "display_name": "默认摘要长度",
        "type": "number",
        "default": "500",
        "options": None,
        "applicable_tools": {"llm_summary": ["max_length"]},
        "description": "LLM 摘要的默认最大长度",
    },
    # ===== 通知(执行失败时读取,非工具参数填充) =====
    {
        "key": "failure_notify_channel",
        "category": "通知",
        "display_name": "失败通知渠道",
        "type": "select",
        "default": "none",
        "options": ["none", "email", "wechat", "dingtalk", "slack"],
        "applicable_tools": {},
        "description": "工作流执行失败时的通知渠道",
    },
    {
        "key": "failure_notify_email",
        "category": "通知",
        "display_name": "失败通知邮箱",
        "type": "text",
        "default": "",
        "options": None,
        "applicable_tools": {},
        "description": "失败通知渠道为 email 时的收件邮箱",
    },
    # ===== 数据管理 =====
    {
        "key": "archive_retention_days",
        "category": "数据管理",
        "display_name": "执行历史保留天数",
        "type": "number",
        "default": "90",
        "options": None,
        "applicable_tools": {},
        "description": "已完成的执行记录保留天数(0=永久保留);失败记录不受此限制,始终保留供复盘",
    },
]


def get_preference_schema() -> list[dict[str, Any]]:
    """返回完整偏好 schema 列表(供 API 返回)"""
    return [dict(item) for item in PREFERENCE_ITEMS]


def get_valid_preference_keys() -> set[str]:
    """返回所有合法偏好 key 集合(用于校验)"""
    return {item["key"] for item in PREFERENCE_ITEMS}


def get_preference_item(key: str) -> dict[str, Any] | None:
    """按 key 查找偏好项定义"""
    for item in PREFERENCE_ITEMS:
        if item["key"] == key:
            return dict(item)
    return None


def get_secret_preference_keys() -> set[str]:
    """返回所有 secret 类型偏好 key 集合(用于脱敏)"""
    return {item["key"] for item in PREFERENCE_ITEMS if item["type"] == "secret"}


def mask_preference_value(value: str) -> str:
    """脱敏:secret 类型已配置时显示 ****后4位。
    短值(≤4 字符)直接返回 ****,避免泄露全部内容。
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


def load_preferences_from_db() -> dict:
    """从 DB 加载所有用户偏好(用于执行期 {{pref.x}} 变量解析与自动填充)。
    best-effort:加载失败返回空 dict,不影响执行。
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        from db.database import SessionLocal
        from db.models import UserPreference
        db = SessionLocal()
        try:
            prefs = db.query(UserPreference).all()
            return {p.key: p.value for p in prefs}
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"加载用户偏好失败: {e}")
        return {}
