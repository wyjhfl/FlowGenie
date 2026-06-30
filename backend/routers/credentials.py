"""凭证配置管理路由 - 集中管理 SMTP/Webhook/Token 等凭证"""
import os
import re
import asyncio
import smtplib
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from dotenv import load_dotenv
import httpx
from db.database import SessionLocal
from db.models import UserPreference
from core.auth import require_admin
from core.ssrf_guard import validate_host

load_dotenv()

router = APIRouter()
logger = logging.getLogger(__name__)

# .env 文件路径（backend/.env）
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# 凭证项定义：key → 类别/显示名/类型
CREDENTIAL_ITEMS = [
    {"key": "SMTP_HOST", "category": "邮件", "display_name": "SMTP 主机", "type": "text"},
    {"key": "SMTP_PORT", "category": "邮件", "display_name": "SMTP 端口", "type": "text"},
    {"key": "SMTP_USER", "category": "邮件", "display_name": "SMTP 用户名", "type": "text"},
    {"key": "SMTP_PASS", "category": "邮件", "display_name": "SMTP 密码", "type": "secret"},
    {"key": "WECHAT_WEBHOOK", "category": "IM推送", "display_name": "企业微信 Webhook URL", "type": "secret"},
    {"key": "SLACK_WEBHOOK", "category": "IM推送", "display_name": "Slack Webhook URL", "type": "secret"},
    {"key": "DINGTALK_WEBHOOK", "category": "IM推送", "display_name": "钉钉 Webhook URL", "type": "secret"},
    {"key": "TELEGRAM_BOT_TOKEN", "category": "IM推送", "display_name": "Telegram Bot Token", "type": "secret"},
    {"key": "TELEGRAM_CHAT_ID", "category": "IM推送", "display_name": "Telegram Chat ID", "type": "text"},
    # LLM 配置(core/llm.py 运行时读取,面板写入 env 后 get_client 自动重建)
    {"key": "LLM_API_KEY", "category": "LLM", "display_name": "LLM API Key", "type": "secret"},
    {"key": "LLM_BASE_URL", "category": "LLM", "display_name": "LLM Base URL", "type": "text"},
    {"key": "LLM_MODEL", "category": "LLM", "display_name": "默认模型", "type": "text"},
    {"key": "LLM_AVAILABLE_MODELS", "category": "LLM", "display_name": "可用模型列表(逗号分隔)", "type": "text"},
    # Notion / 飞书(工具运行时 os.getenv 读取)
    {"key": "NOTION_TOKEN", "category": "Notion", "display_name": "Notion 集成 Token", "type": "secret"},
    {"key": "FEISHU_WEBHOOK_URL", "category": "飞书", "display_name": "飞书机器人 Webhook URL", "type": "text"},
    # 失败通知收件人(core/notify.py 运行时 os.getenv 读取)
    {"key": "FAILURE_NOTIFY_EMAIL", "category": "通知", "display_name": "失败通知收件邮箱", "type": "text"},
    {"key": "GITHUB_TOKEN", "category": "开发工具", "display_name": "GitHub Token", "type": "secret"},
    {"key": "DATABASE_URL", "category": "数据库", "display_name": "数据库连接串", "type": "secret"},
    # 对象存储(C1: tools/object_storage.py 运行时 os.getenv 读取)
    {"key": "S3_ENDPOINT_URL", "category": "对象存储", "display_name": "S3 服务地址(Endpoint URL)", "type": "text"},
    {"key": "S3_ACCESS_KEY", "category": "对象存储", "display_name": "S3 Access Key", "type": "secret"},
    {"key": "S3_SECRET_KEY", "category": "对象存储", "display_name": "S3 Secret Key", "type": "secret"},
    {"key": "S3_BUCKET", "category": "对象存储", "display_name": "S3 默认 Bucket", "type": "text"},
    {"key": "S3_REGION", "category": "对象存储", "display_name": "S3 区域(可选)", "type": "text"},
]

# 合法 key 集合，用于校验
_VALID_KEYS = {item["key"] for item in CREDENTIAL_ITEMS}


def _mask_value(value: str) -> str:
    """脱敏：secret 类型已配置时显示 ****后4位。
    短凭证（≤4 字符）直接返回 ****，避免泄露全部内容。
    """
    if not value:
        return ""
    if len(value) <= 4:
        return "****"
    return "****" + value[-4:]


class CredentialUpdate(BaseModel):
    """凭证更新请求体"""
    key: str
    value: str


def _write_env(key: str, value: str) -> None:
    """更新或追加 key 到 .env 文件（保留注释与空行）"""
    lines = []
    if ENV_PATH.exists():
        lines = ENV_PATH.read_text(encoding="utf-8").splitlines()

    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            existing_key = stripped.split("=", 1)[0].strip()
            if existing_key == key:
                lines[i] = f"{key}={value}"
                found = True
                break

    if not found:
        # 追加到文件末尾（确保前面有空行分隔）
        if lines and lines[-1].strip() != "":
            lines.append("")
        lines.append(f"{key}={value}")

    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


# 凭证 key → 用户偏好 key 的映射（保存凭证时 best-effort 同步到用户偏好）
_CREDENTIAL_TO_PREFERENCE = {
    "SMTP_USER": "email",  # SMTP 用户名通常是 email 地址
    "TELEGRAM_CHAT_ID": "telegram_chat_id",
}


def _sync_preference_from_credential(key: str, value: str) -> None:
    """凭证保存成功后，best-effort 同步到用户偏好（不影响凭证保存）"""
    pref_key = _CREDENTIAL_TO_PREFERENCE.get(key)
    if not pref_key:
        return

    db = SessionLocal()
    try:
        existing = db.query(UserPreference).filter(UserPreference.key == pref_key).first()
        if existing:
            existing.value = value
        else:
            db.add(UserPreference(key=pref_key, value=value))
        db.commit()
    except Exception as e:
        # best-effort：偏好更新失败不影响凭证保存
        logger.warning(f"同步用户偏好失败（key={key}）: {e}")
    finally:
        db.close()


@router.get("")
async def list_credentials():
    """返回所有凭证项及配置状态（值脱敏）"""
    result = []
    for item in CREDENTIAL_ITEMS:
        raw_value = os.environ.get(item["key"], "")
        configured = bool(raw_value)
        if item["type"] == "secret":
            display_value = _mask_value(raw_value)
        else:
            display_value = raw_value
        result.append({
            "key": item["key"],
            "category": item["category"],
            "display_name": item["display_name"],
            "type": item["type"],
            "configured": configured,
            "value": display_value,
        })
    return result


@router.get("/llm-models")
async def get_llm_models():
    """B3: 返回可用 LLM 模型列表(供 NodeInspector 模型下拉选项)
    从 LLM_AVAILABLE_MODELS env 读取(逗号分隔),并包含当前默认模型 LLM_MODEL。
    无需 admin 鉴权(仅读模型名,非敏感信息)。
    """
    available = os.environ.get("LLM_AVAILABLE_MODELS", "")
    default_model = os.environ.get("LLM_MODEL", "")
    # 解析可用模型列表(逗号分隔,去空白与空项)
    models = [m.strip() for m in available.split(",") if m.strip()] if available else []
    # 确保默认模型在列表中(去重)
    if default_model and default_model not in models:
        models.insert(0, default_model)
    return {"models": models, "default": default_model}


@router.put("")
async def update_credential(body: CredentialUpdate, _: None = Depends(require_admin)):
    """更新凭证：写入 .env 并更新运行时环境变量（立即生效）"""
    if body.key not in _VALID_KEYS:
        raise HTTPException(status_code=400, detail=f"未知的凭证 key: {body.key}")

    # 写入前校验凭证值，防止过长或注入换行符
    if len(body.value) > 1024:
        raise HTTPException(status_code=400, detail="凭证值过长")
    if "\n" in body.value or "\r" in body.value:
        raise HTTPException(status_code=400, detail="凭证值不能包含换行符")

    # 更新运行时环境变量（立即生效）
    os.environ[body.key] = body.value

    # 持久化到 .env 文件
    _write_env(body.key, body.value)

    # best-effort 同步用户偏好（如 SMTP_USER → email）
    _sync_preference_from_credential(body.key, body.value)

    return {"success": True}


@router.get("/test")
async def test_credential(
    key: str = Query(..., description="要测试的凭证 key"),
    _: None = Depends(require_admin),
):
    """测试凭证连通性(需 admin token,避免未授权探测)"""
    if key not in _VALID_KEYS:
        raise HTTPException(status_code=400, detail=f"未知的凭证 key: {key}")

    smtp_keys = {"SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS"}
    try:
        if key in smtp_keys:
            return await _test_smtp()
        elif key == "WECHAT_WEBHOOK":
            return await _test_webhook_wechat()
        elif key == "SLACK_WEBHOOK":
            return await _test_webhook_slack()
        elif key == "DINGTALK_WEBHOOK":
            return await _test_webhook_dingtalk()
        elif key == "TELEGRAM_BOT_TOKEN":
            return await _test_telegram()
        elif key == "GITHUB_TOKEN":
            return await _test_github()
        elif key == "DATABASE_URL":
            return await _test_database()
        elif key == "LLM_API_KEY":
            return await _test_llm()
        elif key == "NOTION_TOKEN":
            return await _test_notion()
        elif key == "FEISHU_WEBHOOK_URL":
            return await _test_webhook_feishu()
        elif key == "FAILURE_NOTIFY_EMAIL":
            return await _test_notify_email_format()
        else:
            return {"success": False, "message": f"暂不支持测试 {key}"}
    except Exception as e:
        return {"success": False, "message": str(e)}


def _test_smtp_sync() -> dict:
    """SMTP 连通性测试的同步实现（阻塞调用，需在线程中运行）"""
    host = os.environ.get("SMTP_HOST", "")
    port_str = os.environ.get("SMTP_PORT", "465")
    user = os.environ.get("SMTP_USER", "")
    password = os.environ.get("SMTP_PASS", "")

    if not host or not user:
        return {"success": False, "message": "SMTP 主机或用户名未配置"}

    try:
        port = int(port_str)
    except ValueError:
        return {"success": False, "message": f"SMTP 端口不是有效数字: {port_str}"}

    # SSRF 防护:校验 SMTP 主机(DNS 解析 + 内网 IP 检查),内网主机拒绝连接
    validate_host(host)

    server = None
    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=5)
        else:
            server = smtplib.SMTP(host, port, timeout=5)
            server.starttls()
        server.login(user, password)
        return {"success": True, "message": f"SMTP 连接成功 ({host}:{port})"}
    except Exception as e:
        return {"success": False, "message": f"SMTP 连接失败: {e}"}
    finally:
        if server is not None:
            try:
                server.quit()
            except Exception:
                pass


async def _test_smtp() -> dict:
    """测试 SMTP 连通性（非阻塞：同步阻塞调用放到线程池执行）"""
    return await asyncio.to_thread(_test_smtp_sync)


async def _test_webhook_wechat() -> dict:
    """测试企业微信 Webhook 连通性"""
    url = os.environ.get("WECHAT_WEBHOOK", "")
    if not url:
        return {"success": False, "message": "企业微信 Webhook 未配置"}
    payload = {"msgtype": "text", "text": {"content": "FlowGenie 连通性测试"}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
        if result.get("errcode", 0) == 0:
            return {"success": True, "message": "企业微信 Webhook 连通正常"}
        return {"success": False, "message": f"企业微信返回错误: {result.get('errmsg', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"企业微信 Webhook 测试失败: {e}"}


async def _test_webhook_slack() -> dict:
    """测试 Slack Webhook 连通性"""
    url = os.environ.get("SLACK_WEBHOOK", "")
    if not url:
        return {"success": False, "message": "Slack Webhook 未配置"}
    payload = {"text": "FlowGenie 连通性测试"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
        if resp.status_code == 200:
            return {"success": True, "message": "Slack Webhook 连通正常"}
        return {"success": False, "message": f"Slack 返回状态码 {resp.status_code}: {resp.text}"}
    except Exception as e:
        return {"success": False, "message": f"Slack Webhook 测试失败: {e}"}


async def _test_webhook_dingtalk() -> dict:
    """测试钉钉 Webhook 连通性"""
    url = os.environ.get("DINGTALK_WEBHOOK", "")
    if not url:
        return {"success": False, "message": "钉钉 Webhook 未配置"}
    payload = {"msgtype": "text", "text": {"content": "FlowGenie 连通性测试"}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
        if result.get("errcode", 0) == 0:
            return {"success": True, "message": "钉钉 Webhook 连通正常"}
        return {"success": False, "message": f"钉钉返回错误: {result.get('errmsg', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"钉钉 Webhook 测试失败: {e}"}


async def _test_telegram() -> dict:
    """测试 Telegram Bot Token 连通性"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return {"success": False, "message": "Telegram Bot Token 未配置"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            result = resp.json()
        if result.get("ok"):
            bot_name = result.get("result", {}).get("username", "")
            return {"success": True, "message": f"Telegram Bot 连通正常: @{bot_name}"}
        return {"success": False, "message": f"Telegram 返回错误: {result.get('description', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"Telegram 测试失败: {e}"}


async def _test_github() -> dict:
    """测试 GitHub Token 有效性"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return {"success": False, "message": "GitHub Token 未配置"}
    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "FlowGenie/1.0",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.github.com/user", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            login = data.get("login", "")
            return {"success": True, "message": f"GitHub Token 有效: @{login}"}
        return {"success": False, "message": f"GitHub 返回状态码 {resp.status_code}"}
    except Exception as e:
        return {"success": False, "message": f"GitHub 测试失败: {e}"}


def _test_database_sync() -> dict:
    """数据库连通性测试的同步实现（阻塞调用，需在线程中运行）"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        return {"success": False, "message": "数据库连接串未配置"}
    try:
        from sqlalchemy import create_engine, text
        engine = create_engine(url)
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            engine.dispose()
        return {"success": True, "message": "数据库连接成功"}
    except Exception as e:
        return {"success": False, "message": f"数据库连接失败: {e}"}


async def _test_database() -> dict:
    """测试数据库连通性（非阻塞：同步阻塞调用放到线程池执行）"""
    return await asyncio.to_thread(_test_database_sync)


# 邮箱格式正则(用于 FAILURE_NOTIFY_EMAIL 校验)
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _test_llm_sync() -> dict:
    """LLM 连通性测试的同步实现:发一个最小 chat 请求验证 API Key/Base URL/模型可用"""
    from core.llm import has_api_key, chat
    if not has_api_key():
        return {"success": False, "message": "LLM API Key 未配置"}
    try:
        # 最小请求:max_tokens=5 降低成本,temperature=0 提高稳定性
        chat("You are a connectivity test.", "ping", max_tokens=5, temperature=0)
        model = os.environ.get("LLM_MODEL", "agnes-2.0-flash")
        return {"success": True, "message": f"LLM 连通正常,当前模型: {model}"}
    except Exception as e:
        return {"success": False, "message": f"LLM 调用失败: {e}"}


async def _test_llm() -> dict:
    """测试 LLM 连通性(非阻塞:同步阻塞调用放到线程池执行)"""
    return await asyncio.to_thread(_test_llm_sync)


async def _test_notion() -> dict:
    """测试 Notion Token 有效性:调用 /v1/users/me"""
    token = os.environ.get("NOTION_TOKEN", "")
    if not token:
        return {"success": False, "message": "Notion Token 未配置"}
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://api.notion.com/v1/users/me", headers=headers)
        if resp.status_code == 200:
            data = resp.json()
            name = data.get("name", "") or data.get("bot", {}).get("owner", {}).get("user", {}).get("name", "")
            return {"success": True, "message": f"Notion Token 有效: {name}"}
        return {"success": False, "message": f"Notion 返回状态码 {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        return {"success": False, "message": f"Notion 测试失败: {e}"}


async def _test_webhook_feishu() -> dict:
    """测试飞书机器人 Webhook 连通性:发一条测试文本消息"""
    url = os.environ.get("FEISHU_WEBHOOK_URL", "")
    if not url:
        return {"success": False, "message": "飞书 Webhook 未配置"}
    payload = {"msg_type": "text", "content": {"text": "FlowGenie 连通性测试"}}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload)
            result = resp.json()
        # 飞书 webhook 成功返回 code=0(旧版用 StatusCode=200)
        if result.get("code", result.get("StatusCode", -1)) in (0, 200):
            return {"success": True, "message": "飞书 Webhook 连通正常"}
        return {"success": False, "message": f"飞书返回错误: {result.get('msg', '未知错误')}"}
    except Exception as e:
        return {"success": False, "message": f"飞书 Webhook 测试失败: {e}"}


async def _test_notify_email_format() -> dict:
    """失败通知收件邮箱格式校验(纯本地校验,不发网络请求)"""
    email = os.environ.get("FAILURE_NOTIFY_EMAIL", "")
    if not email:
        return {"success": False, "message": "失败通知邮箱未配置"}
    if not _EMAIL_RE.match(email):
        return {"success": False, "message": f"邮箱格式无效: {email}"}
    # 提示 SMTP 是否就绪(邮件通知依赖 SMTP 发件配置)
    smtp_ready = bool(os.environ.get("SMTP_HOST") and os.environ.get("SMTP_USER"))
    hint = "" if smtp_ready else "(提示:SMTP 未配置,邮件通知无法实际发送)"
    return {"success": True, "message": f"邮箱格式有效: {email} {hint}".strip()}
