"""全局失败通知 - 工作流执行失败时自动发送通知"""
import os
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session
from core.error_sanitize import sanitize_error_text

logger = logging.getLogger(__name__)


async def send_failure_notification(
    workflow_name: str,
    run_id: str,
    error: str,
    channel: str,
    steps_result: dict = None,
    notify_email: str = "",
):
    """
    工作流失败时发送通知
    :param channel: none/email/wechat/dingtalk/slack/telegram
    :param notify_email: 邮件收件人（优先于环境变量 FAILURE_NOTIFY_EMAIL）

    注:error 应由 caller 脱敏;此处再脱敏一次作为双重防护,
    避免因 caller 遗漏导致敏感信息泄露到外部通知渠道。
    """
    if channel == "none" or not channel:
        return

    # 双重脱敏:防止 caller 遗漏导致泄露
    safe_error = sanitize_error_text(error or "")

    # 构造通知内容
    # 通知时间用于用户展示，保留本地时区（存储字段已统一使用 UTC）
    content = f"""❌ 工作流执行失败

工作流: {workflow_name}
执行ID: {run_id}
错误: {safe_error}
时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
    try:
        if channel == "email":
            from tools.send_email import execute as send_email
            # 收件人优先取参数，其次环境变量
            to = notify_email or os.getenv("FAILURE_NOTIFY_EMAIL", "")
            if to:
                await send_email(
                    {"to": to, "subject": f"[FlowGenie] 工作流失败: {workflow_name}", "content": content},
                    None,
                )
                logger.info(f"失败通知已发送 via {channel}")
            else:
                logger.warning("失败通知渠道为 email，但未配置收件人")
        elif channel == "wechat":
            from tools.send_wechat import execute as send_wechat
            await send_wechat({"content": content, "msg_type": "text"}, None)
            logger.info(f"失败通知已发送 via {channel}")
        elif channel == "dingtalk":
            from tools.send_dingtalk import execute as send_dingtalk
            await send_dingtalk({"content": content, "msg_type": "text"}, None)
            logger.info(f"失败通知已发送 via {channel}")
        elif channel == "slack":
            from tools.send_slack import execute as send_slack
            await send_slack({"text": content}, None)
            logger.info(f"失败通知已发送 via {channel}")
        elif channel == "telegram":
            from tools.send_telegram import execute as send_telegram
            chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
            if chat_id:
                await send_telegram(
                    {"chat_id": chat_id, "text": content, "parse_mode": "text"}, None
                )
                logger.info(f"失败通知已发送 via {channel}")
            else:
                logger.warning("失败通知渠道为 telegram，但未配置 chat_id")
        else:
            logger.warning(f"未知的通知渠道: {channel}")
    except Exception as e:
        logger.error(f"发送失败通知失败: {e}")


async def maybe_notify_failure(
    db: Session,
    workflow_name: str,
    run_id: str,
    status: str,
    error: str,
    steps_result: dict = None,
):
    """工作流执行非 success 时按用户偏好发送失败通知（异常不影响主流程）

    从 user_preferences 表读取 failure_notify_channel 和 failure_notify_email。
    :param db: SQLAlchemy 会话
    :param status: 执行状态，success 时跳过
    :param error: 错误信息
    :param steps_result: 各步骤执行结果
    """
    if status == "success":
        return
    try:
        from db.models import UserPreference
        prefs = db.query(UserPreference).filter(
            UserPreference.key.in_(["failure_notify_channel", "failure_notify_email"])
        ).all()
        pref_map = {p.key: p.value for p in prefs}
        channel = pref_map.get("failure_notify_channel", "none")
        notify_email = pref_map.get("failure_notify_email", "")
        if channel and channel != "none":
            await send_failure_notification(
                workflow_name=workflow_name,
                run_id=run_id,
                error=error or "",
                channel=channel,
                steps_result=steps_result,
                notify_email=notify_email,
            )
    except Exception as e:
        logger.warning(f"发送失败通知失败: {e}")
