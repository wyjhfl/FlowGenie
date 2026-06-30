"""credentials API 集成测试 - 凭证列表脱敏 / 更新校验 / admin token / 连通性测试

覆盖:
- GET 列表:secret 类型脱敏(****后4位)、text 类型明文、未配置项 configured=False
- PUT 更新:成功写入运行时环境变量(mock 掉 .env 文件写入与偏好同步)
- PUT 校验:未知 key → 400;含换行符 → 400
- admin token:配置 FLOWGENIE_ADMIN_TOKEN 后未携带 X-Admin-Token → 403
- GET /test:未知 key → 400;mock _test_smtp 返回连通性结果
"""
import os
import pytest
from unittest.mock import patch, AsyncMock


@pytest.mark.asyncio
async def test_list_credentials_secret_masking(client, monkeypatch):
    """secret 类型凭证列表返回脱敏值,text 类型返回明文"""
    monkeypatch.setenv("SMTP_PASS", "secret123456")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    resp = await client.get("/api/credentials")
    assert resp.status_code == 200
    items = {it["key"]: it for it in resp.json()}

    smtp_pass = items["SMTP_PASS"]
    assert smtp_pass["type"] == "secret"
    assert smtp_pass["configured"] is True
    # 脱敏:**** + 后4位,不泄露明文
    assert smtp_pass["value"] == "****3456"
    assert "secret123456" not in smtp_pass["value"]

    smtp_host = items["SMTP_HOST"]
    assert smtp_host["type"] == "text"
    assert smtp_host["configured"] is True
    assert smtp_host["value"] == "smtp.example.com"  # text 类型不脱敏


@pytest.mark.asyncio
async def test_list_credentials_unconfigured(client, monkeypatch):
    """未配置的凭证 configured=False,value 为空"""
    monkeypatch.delenv("SLACK_WEBHOOK", raising=False)
    resp = await client.get("/api/credentials")
    assert resp.status_code == 200
    items = {it["key"]: it for it in resp.json()}
    slack = items["SLACK_WEBHOOK"]
    assert slack["configured"] is False
    assert slack["value"] == ""


@pytest.mark.asyncio
async def test_update_credential_success(client, monkeypatch):
    """更新凭证成功:写入运行时环境变量(mock 掉 .env 文件写入与偏好同步,避免副作用)"""
    monkeypatch.setenv("SMTP_HOST", "")
    with patch("routers.credentials._write_env") as mock_write, \
         patch("routers.credentials._sync_preference_from_credential"):
        resp = await client.put(
            "/api/credentials",
            json={"key": "SMTP_HOST", "value": "smtp.new.com"},
        )
    assert resp.status_code == 200
    assert resp.json() == {"success": True}
    # 运行时环境变量立即生效
    assert os.environ.get("SMTP_HOST") == "smtp.new.com"
    mock_write.assert_called_once_with("SMTP_HOST", "smtp.new.com")


@pytest.mark.asyncio
async def test_update_credential_unknown_key_rejected(client):
    """未知凭证 key 返回 400"""
    resp = await client.put(
        "/api/credentials",
        json={"key": "NOT_A_REAL_KEY", "value": "x"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_credential_rejects_newline(client, monkeypatch):
    """含换行符的值被拒绝(防止 .env 注入)"""
    monkeypatch.setenv("SMTP_PASS", "")
    with patch("routers.credentials._write_env"), \
         patch("routers.credentials._sync_preference_from_credential"):
        resp = await client.put(
            "/api/credentials",
            json={"key": "SMTP_PASS", "value": "abc\ndef"},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_update_credential_requires_admin_token(client, monkeypatch):
    """配置 admin token 后,未携带 X-Admin-Token 返回 403"""
    monkeypatch.setenv("FLOWGENIE_ADMIN_TOKEN", "admin-secret")
    with patch("routers.credentials._write_env"), \
         patch("routers.credentials._sync_preference_from_credential"):
        resp = await client.put(
            "/api/credentials",
            json={"key": "SMTP_HOST", "value": "smtp.x.com"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_test_credential_unknown_key_rejected(client):
    """连通性测试端点对未知 key 返回 400"""
    resp = await client.get("/api/credentials/test", params={"key": "NOT_A_REAL_KEY"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_test_credential_smtp_mocked(client):
    """连通性测试端点返回 SMTP 结果(mock 网络调用,验证 HTTP 层行为)"""
    with patch("routers.credentials._test_smtp", new_callable=AsyncMock) as mock_smtp:
        mock_smtp.return_value = {
            "success": True,
            "message": "SMTP 连接成功 (smtp.example.com:465)",
        }
        resp = await client.get("/api/credentials/test", params={"key": "SMTP_HOST"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "SMTP" in data["message"]
    mock_smtp.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_credentials_includes_new_items(client, monkeypatch):
    """新增凭证项(LLM/Notion/飞书/通知)出现在列表,且 type/category 正确"""
    monkeypatch.setenv("LLM_API_KEY", "sk-abcdef123456")
    monkeypatch.setenv("LLM_MODEL", "agnes-2.0-flash")
    monkeypatch.setenv("FEISHU_WEBHOOK_URL", "https://open.feishu.cn/open-apis/bot/v2/hook/x")
    monkeypatch.setenv("FAILURE_NOTIFY_EMAIL", "user@example.com")
    monkeypatch.setenv("NOTION_TOKEN", "secret_abc123456789")
    resp = await client.get("/api/credentials")
    assert resp.status_code == 200
    items = {it["key"]: it for it in resp.json()}

    # LLM_API_KEY 为 secret,脱敏显示
    llm_key = items["LLM_API_KEY"]
    assert llm_key["type"] == "secret"
    assert llm_key["category"] == "LLM"
    assert llm_key["configured"] is True
    assert llm_key["value"] == "****3456"
    assert "sk-abcdef123456" not in llm_key["value"]

    # LLM_MODEL 为 text,明文
    assert items["LLM_MODEL"]["type"] == "text"
    assert items["LLM_MODEL"]["value"] == "agnes-2.0-flash"

    # LLM_AVAILABLE_MODELS 存在(LLM 类)
    assert "LLM_AVAILABLE_MODELS" in items
    assert items["LLM_AVAILABLE_MODELS"]["category"] == "LLM"

    # NOTION_TOKEN 为 secret,脱敏
    notion = items["NOTION_TOKEN"]
    assert notion["type"] == "secret"
    assert notion["category"] == "Notion"
    assert notion["value"] == "****6789"

    # FEISHU_WEBHOOK_URL 为 text,明文
    feishu = items["FEISHU_WEBHOOK_URL"]
    assert feishu["type"] == "text"
    assert feishu["category"] == "飞书"
    assert feishu["value"].endswith("/hook/x")

    # FAILURE_NOTIFY_EMAIL 为 text,明文
    notify = items["FAILURE_NOTIFY_EMAIL"]
    assert notify["type"] == "text"
    assert notify["category"] == "通知"
    assert notify["value"] == "user@example.com"


@pytest.mark.asyncio
async def test_test_credential_llm_mocked(client):
    """LLM_API_KEY 连通性测试端点(mock _test_llm)"""
    with patch("routers.credentials._test_llm", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = {"success": True, "message": "LLM 连通正常,当前模型: agnes-2.0-flash"}
        resp = await client.get("/api/credentials/test", params={"key": "LLM_API_KEY"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "LLM" in data["message"]
    mock_llm.assert_awaited_once()


@pytest.mark.asyncio
async def test_test_credential_notion_mocked(client):
    """NOTION_TOKEN 连通性测试端点(mock _test_notion)"""
    with patch("routers.credentials._test_notion", new_callable=AsyncMock) as mock_notion:
        mock_notion.return_value = {"success": True, "message": "Notion Token 有效: mybot"}
        resp = await client.get("/api/credentials/test", params={"key": "NOTION_TOKEN"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_notion.assert_awaited_once()


@pytest.mark.asyncio
async def test_test_credential_feishu_mocked(client):
    """FEISHU_WEBHOOK_URL 连通性测试端点(mock _test_webhook_feishu)"""
    with patch("routers.credentials._test_webhook_feishu", new_callable=AsyncMock) as mock_feishu:
        mock_feishu.return_value = {"success": True, "message": "飞书 Webhook 连通正常"}
        resp = await client.get("/api/credentials/test", params={"key": "FEISHU_WEBHOOK_URL"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    mock_feishu.assert_awaited_once()


@pytest.mark.asyncio
async def test_test_credential_notify_email_format(client, monkeypatch):
    """FAILURE_NOTIFY_EMAIL 格式校验:有效邮箱返回成功"""
    monkeypatch.setenv("FAILURE_NOTIFY_EMAIL", "user@example.com")
    resp = await client.get("/api/credentials/test", params={"key": "FAILURE_NOTIFY_EMAIL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "user@example.com" in data["message"]


@pytest.mark.asyncio
async def test_test_credential_notify_email_invalid(client, monkeypatch):
    """FAILURE_NOTIFY_EMAIL 格式校验:无效邮箱返回失败"""
    monkeypatch.setenv("FAILURE_NOTIFY_EMAIL", "not-an-email")
    resp = await client.get("/api/credentials/test", params={"key": "FAILURE_NOTIFY_EMAIL"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "无效" in data["message"]


@pytest.mark.asyncio
async def test_update_credential_new_keys_accepted(client, monkeypatch):
    """新增凭证 key 可通过 PUT 更新(mock .env 写入与偏好同步)"""
    monkeypatch.setenv("LLM_API_KEY", "")
    with patch("routers.credentials._write_env") as mock_write, \
         patch("routers.credentials._sync_preference_from_credential"):
        resp = await client.put(
            "/api/credentials",
            json={"key": "LLM_API_KEY", "value": "sk-newkey123456"},
        )
    assert resp.status_code == 200
    assert os.environ.get("LLM_API_KEY") == "sk-newkey123456"
    mock_write.assert_called_once_with("LLM_API_KEY", "sk-newkey123456")


# ===== B3: LLM 模型列表端点 =====

@pytest.mark.asyncio
async def test_llm_models_returns_models_and_default(client, monkeypatch):
    """B3: GET /api/credentials/llm-models 返回可用模型列表与默认模型"""
    monkeypatch.setenv("LLM_AVAILABLE_MODELS", "agnes-2.0-flash, agnes-2.0-mini, gpt-4o")
    monkeypatch.setenv("LLM_MODEL", "agnes-2.0-flash")
    resp = await client.get("/api/credentials/llm-models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default"] == "agnes-2.0-flash"
    # 逗号分隔解析,去空白
    assert "agnes-2.0-flash" in data["models"]
    assert "agnes-2.0-mini" in data["models"]
    assert "gpt-4o" in data["models"]
    # 默认模型不应重复出现在列表中
    assert data["models"].count("agnes-2.0-flash") == 1


@pytest.mark.asyncio
async def test_llm_models_includes_default_when_not_in_list(client, monkeypatch):
    """B3: 默认模型不在 LLM_AVAILABLE_MODELS 时自动插入列表头部"""
    monkeypatch.setenv("LLM_AVAILABLE_MODELS", "agnes-2.0-mini, gpt-4o")
    monkeypatch.setenv("LLM_MODEL", "agnes-2.0-flash")
    resp = await client.get("/api/credentials/llm-models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["default"] == "agnes-2.0-flash"
    # 默认模型被自动加入列表(位于首位)
    assert data["models"][0] == "agnes-2.0-flash"
    assert "agnes-2.0-mini" in data["models"]


@pytest.mark.asyncio
async def test_llm_models_empty_when_unconfigured(client, monkeypatch):
    """B3: 未配置任何模型时返回空列表与空默认"""
    monkeypatch.delenv("LLM_AVAILABLE_MODELS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    resp = await client.get("/api/credentials/llm-models")
    assert resp.status_code == 200
    data = resp.json()
    assert data["models"] == []
    assert data["default"] == ""


@pytest.mark.asyncio
async def test_llm_models_no_admin_required(client, monkeypatch):
    """B3: llm-models 端点无需 admin token(仅返回模型名,非敏感信息)"""
    monkeypatch.setenv("FLOWGENIE_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("LLM_MODEL", "agnes-2.0-flash")
    resp = await client.get("/api/credentials/llm-models")
    # 不应返回 403(与其他需 admin 的端点不同)
    assert resp.status_code == 200
