"""SSRF 防护覆盖测试

验证所有出站 HTTP/SMTP 工具在发起请求前调用 ssrf_guard 校验:
- 内网目标(127.0.0.1 / 169.254.169.254 / 10.0.0.1 等)被 ValueError 拦截
- 外网目标不被拦截(validate_url / validate_host 被调用且通过)
- github_api:endpoint 注入拼接后仍校验完整 URL

测试技巧:
- mock `core.ssrf_guard._sync_resolve` 控制解析结果,保证确定性(不依赖真实 DNS / 网络)
  * return_value="127.0.0.1" 模拟解析到内网 → 拦截
  * return_value="1.1.1.1" 模拟解析到公网 → 放行
- mock `httpx.AsyncClient` / `smtplib.SMTP_SSL` 避免真实网络请求
- IP 字面量的真实解析路径(loopback 127.0.0.1 / 公网 1.1.1.1)单独用真实 gethostbyname 覆盖
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from core.ssrf_guard import validate_url, validate_host
from tools.rss_reader import execute as rss_execute
from tools.github_api import execute as github_execute
from tools.feishu_api import execute as feishu_execute
from tools.notion_api import execute as notion_execute
from tools.send_wechat import execute as wechat_execute
from tools.send_slack import execute as slack_execute
from tools.send_dingtalk import execute as dingtalk_execute
from tools.send_telegram import execute as telegram_execute
from tools.send_email import execute as email_execute


# ---------------------------------------------------------------------------
# 辅助:构造 httpx.AsyncClient 的 mock
# ---------------------------------------------------------------------------

def _httpx_mock(response):
    """返回一个替换 `httpx.AsyncClient` 的 mock,使
    `async with httpx.AsyncClient(...) as client` 生效,且
    client.get / client.post / client.request 均返回 `response`。"""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.request = AsyncMock(return_value=response)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=None)
    return MagicMock(return_value=cm)


def _response(status_code=200, text="", content=b"", json_data=None, headers=None):
    """构造一个具有常用属性的 httpx.Response mock"""
    resp = MagicMock()
    resp.status_code = status_code
    resp.text = text
    resp.content = content
    resp.json = MagicMock(return_value=json_data if json_data is not None else {})
    resp.headers = headers if headers is not None else {}
    return resp


# ---------------------------------------------------------------------------
# 1. ssrf_guard 直接单测
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/",
    "http://169.254.169.254/",
    "http://10.0.0.1/",
    "http://192.168.1.1/",
])
async def test_validate_url_blocks_internal(url):
    """内网 IP 字面量被拦截(mock 解析器回显主机,确定性验证 _is_ip_blocked)"""
    with patch("core.ssrf_guard._sync_resolve", side_effect=lambda h: h):
        with pytest.raises(ValueError):
            await validate_url(url)


@pytest.mark.asyncio
async def test_validate_url_blocks_loopback_real_dns():
    """真实解析路径:127.0.0.1 是 IP 字面量,gethostbyname 直接返回,无需 mock DNS"""
    with pytest.raises(ValueError):
        await validate_url("http://127.0.0.1/")


@pytest.mark.asyncio
async def test_validate_url_blocks_bad_protocol():
    """非 http/https 协议被拒"""
    with pytest.raises(ValueError):
        await validate_url("ftp://example.com/")


@pytest.mark.asyncio
async def test_validate_url_allows_public_ip_literal():
    """公网 IP 字面量放行(1.1.1.1 真实解析,无网络依赖)"""
    ip = await validate_url("https://1.1.1.1/")
    assert ip == "1.1.1.1"


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "192.168.0.1"])
def test_validate_host_blocks_internal(host):
    """validate_host 拦截内网主机"""
    with patch("core.ssrf_guard._sync_resolve", side_effect=lambda h: h):
        with pytest.raises(ValueError):
            validate_host(host)


def test_validate_host_blocks_empty():
    """空主机被拒"""
    with pytest.raises(ValueError):
        validate_host("")


def test_validate_host_allows_public_ip_literal():
    """validate_host 放行公网主机(真实解析)"""
    assert validate_host("1.1.1.1") == "1.1.1.1"


# ---------------------------------------------------------------------------
# 2. 各工具:内网目标被拦截
#    统一 mock _sync_resolve -> "127.0.0.1",强制解析到内网
# ---------------------------------------------------------------------------

INTERNAL_TOOL_CASES = [
    ("rss", rss_execute, {"feed_url": "http://127.0.0.1:8000/feed"}),
    ("feishu", feishu_execute, {"content": "x", "webhook_url": "http://169.254.169.254/"}),
    ("notion", notion_execute, {"database_id": "db", "properties": {"k": "v"}, "token": "t"}),
    ("wechat", wechat_execute, {"webhook_url": "http://10.0.0.1/", "content": "x"}),
    ("slack", slack_execute, {"webhook_url": "http://127.0.0.1/", "text": "x"}),
    ("dingtalk", dingtalk_execute, {"webhook_url": "http://169.254.169.254/", "content": "x"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "_,execute,params",
    INTERNAL_TOOL_CASES,
    ids=[c[0] for c in INTERNAL_TOOL_CASES],
)
async def test_tool_internal_url_blocked(_, execute, params):
    """传入内网 URL 的工具应 raise ValueError(在 httpx 请求前拦截)"""
    with patch("core.ssrf_guard._sync_resolve", return_value="127.0.0.1"):
        with pytest.raises(ValueError):
            await execute(params, None)


@pytest.mark.asyncio
async def test_github_api_internal_blocked():
    """github_api:固定 host 被强制解析到内网时拦截"""
    with patch("core.ssrf_guard._sync_resolve", return_value="127.0.0.1"):
        with pytest.raises(ValueError):
            await github_execute({"endpoint": "/user"}, None)


@pytest.mark.asyncio
async def test_send_telegram_internal_blocked(monkeypatch):
    """send_telegram:固定 host 被强制解析到内网时拦截"""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    with patch("core.ssrf_guard._sync_resolve", return_value="127.0.0.1"):
        with pytest.raises(ValueError):
            await telegram_execute({"chat_id": "1", "text": "x"}, None)


# ---------------------------------------------------------------------------
# 3. 各工具:外网目标不被拦截(mock httpx,验证 validate_url 被调用且通过)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rss_reader_external_allowed():
    xml = (b'<?xml version="1.0"?><rss version="2.0"><channel>'
           b'<item><title>t</title><link>l</link>'
           b'<pubDate>d</pubDate><description>s</description></item>'
           b'</channel></rss>')
    resp = _response(status_code=200, content=xml)
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await rss_execute({"feed_url": "https://example.com/feed.xml"}, None)
    assert result["count"] == 1
    mock_res.assert_called_once_with("example.com")


@pytest.mark.asyncio
async def test_github_api_external_allowed():
    resp = _response(status_code=200, json_data={"login": "x"},
                     headers={"X-RateLimit-Remaining": "60"})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await github_execute({"endpoint": "/user"}, None)
    assert result["status_code"] == 200
    assert result["rate_limit_remaining"] == 60
    mock_res.assert_called_once_with("api.github.com")


@pytest.mark.asyncio
async def test_feishu_api_external_allowed():
    resp = _response(status_code=200, json_data={"code": 0})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await feishu_execute(
            {"content": "x", "webhook_url": "https://open.feishu.cn/hook"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("open.feishu.cn")


@pytest.mark.asyncio
async def test_notion_api_external_allowed():
    resp = _response(status_code=200, json_data={"id": "p1", "url": "http://n"})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await notion_execute(
            {"database_id": "db", "properties": {"name": "v"}, "token": "tok"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("api.notion.com")


@pytest.mark.asyncio
async def test_send_wechat_external_allowed():
    resp = _response(status_code=200, json_data={"errcode": 0})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await wechat_execute(
            {"webhook_url": "https://qyapi.weixin.qq.com/hook", "content": "x"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("qyapi.weixin.qq.com")


@pytest.mark.asyncio
async def test_send_slack_external_allowed():
    resp = _response(status_code=200, text="ok")
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await slack_execute(
            {"webhook_url": "https://hooks.slack.com/hook", "text": "x"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("hooks.slack.com")


@pytest.mark.asyncio
async def test_send_dingtalk_external_allowed():
    resp = _response(status_code=200, json_data={"errcode": 0})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await dingtalk_execute(
            {"webhook_url": "https://oapi.dingtalk.com/hook", "content": "x"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("oapi.dingtalk.com")


@pytest.mark.asyncio
async def test_send_telegram_external_allowed(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:abc")
    resp = _response(status_code=200,
                     json_data={"ok": True, "result": {"message_id": 42, "date": 2}})
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", _httpx_mock(resp)):
        result = await telegram_execute({"chat_id": "1", "text": "x"}, None)
    assert result["message_id"] == 42
    mock_res.assert_called_once_with("api.telegram.org")


# ---------------------------------------------------------------------------
# 4. github_api:endpoint 注入测试
#    endpoint=//evil.com 拼接后 host 仍为 api.github.com,validate_url 校验完整 URL
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_github_api_endpoint_injection_validates_full_url():
    resp = _response(status_code=200, json_data={}, headers={})
    httpx_mock = _httpx_mock(resp)
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("httpx.AsyncClient", httpx_mock):
        result = await github_execute({"endpoint": "//evil.com"}, None)
    # host 仍为 api.github.com(//evil.com 被当作路径),校验通过
    mock_res.assert_called_once_with("api.github.com")
    # httpx 收到的是拼接后的完整 URL
    client = httpx_mock.return_value.__aenter__.return_value
    client.request.assert_called_once()
    called_url = client.request.call_args.args[1]
    assert called_url == "https://api.github.com//evil.com"
    assert result["status_code"] == 200


# ---------------------------------------------------------------------------
# 5. send_email:validate_host(SMTP 场景)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_email_internal_smtp_host_blocked(monkeypatch):
    """SMTP 主机解析到内网 → 拦截"""
    monkeypatch.setenv("SMTP_HOST", "smtp.evil.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    with patch("core.ssrf_guard._sync_resolve", return_value="127.0.0.1"):
        with pytest.raises(ValueError):
            await email_execute(
                {"to": "a@b.com", "subject": "s", "content": "c"}, None)


@pytest.mark.asyncio
async def test_send_email_external_smtp_host_allowed(monkeypatch):
    """SMTP 主机解析到公网 → 放行(mock smtplib 避免真实连接)"""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    fake_server = MagicMock()
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("smtplib.SMTP_SSL", return_value=fake_server):
        result = await email_execute(
            {"to": "a@b.com", "subject": "s", "content": "c"}, None)
    assert result["success"] is True
    mock_res.assert_called_once_with("smtp.example.com")
    fake_server.login.assert_called_once_with("u", "p")
    fake_server.sendmail.assert_called_once()


# ---------------------------------------------------------------------------
# 6. credentials._test_smtp_sync:validate_host 接入
# ---------------------------------------------------------------------------

def test_test_smtp_sync_internal_host_blocked(monkeypatch):
    """SMTP 连通性测试:主机解析到内网 → ValueError(路由层会捕获转为失败结果)"""
    monkeypatch.setenv("SMTP_HOST", "smtp.evil.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    from routers.credentials import _test_smtp_sync
    with patch("core.ssrf_guard._sync_resolve", return_value="127.0.0.1"):
        with pytest.raises(ValueError):
            _test_smtp_sync()


def test_test_smtp_sync_external_host_allowed(monkeypatch):
    """SMTP 连通性测试:主机解析到公网 → 放行(mock smtplib)"""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "465")
    monkeypatch.setenv("SMTP_USER", "u")
    monkeypatch.setenv("SMTP_PASS", "p")
    fake_server = MagicMock()
    from routers.credentials import _test_smtp_sync
    with patch("core.ssrf_guard._sync_resolve", return_value="1.1.1.1") as mock_res, \
            patch("smtplib.SMTP_SSL", return_value=fake_server):
        result = _test_smtp_sync()
    assert result["success"] is True
    mock_res.assert_called_once_with("smtp.example.com")
