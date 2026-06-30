"""发送邮件工具 - smtplib SMTP"""
import os
import asyncio
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from core.ssrf_guard import validate_host


def _send_sync(smtp_host: str, smtp_port: int, smtp_user: str, smtp_pass: str,
               to: str, msg_as_string: str) -> dict:
    """同步发送邮件（SMTP_SSL/login/sendmail），在线程池中执行"""
    # SSRF 防护:校验 SMTP 主机(DNS 解析 + 内网 IP 检查),内网主机拒绝连接
    validate_host(smtp_host)
    # 发送（SSL），确保连接在任何情况下都关闭
    server = None
    try:
        if smtp_port == 465:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to], msg_as_string)
        return {"success": True, "message": f"邮件已发送至 {to}"}
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


async def execute(params: dict, context) -> dict:
    """
    发送邮件
    :param params: { to, subject, content, content_type }
    :return: { success, message }
    """
    to = params.get("to", "")
    subject = params.get("subject", "FlowGenie 工作流通知")
    content = params.get("content", "")
    content_type = params.get("content_type", "plain")  # plain | html

    if not to:
        raise ValueError("to 参数不能为空")

    # 空数据容错：空内容跳过发送，返回有意义的空结果
    if not content:
        return {"success": False, "message": "邮件内容为空，已跳过发送"}

    # content 可能是变量插值后的对象，转为字符串
    if not isinstance(content, str):
        import json
        content = json.dumps(content, ensure_ascii=False, default=str)

    # 从环境变量读取 SMTP 配置（SMTP_* 为主，EMAIL_SMTP_* 为兼容旧 .env 的 fallback）
    smtp_host = os.getenv("SMTP_HOST", "") or os.getenv("EMAIL_SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "") or os.getenv("EMAIL_SMTP_PORT", "465"))
    smtp_user = os.getenv("SMTP_USER", "") or os.getenv("EMAIL_SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "") or os.getenv("EMAIL_SMTP_PASS", "")

    if not smtp_host or not smtp_user:
        raise ValueError("未配置 SMTP，请在凭证面板配置 SMTP 主机/用户名/密码，或在 .env 设置 SMTP_HOST/SMTP_USER/SMTP_PASS")

    # 构建邮件
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(content, content_type, "utf-8"))

    # 在线程池中执行同步 SMTP 发送，避免阻塞事件循环
    return await asyncio.to_thread(
        _send_sync, smtp_host, smtp_port, smtp_user, smtp_pass, to, msg.as_string()
    )
