"""C1: 对象存储工具单元测试

验证:
- object_storage_upload: 上传成功 / key 规范化 / SSRF 防护 / 配置缺失兜底 / 空 content
- object_storage_download: 下载成功(text/binary 编码) / key 校验
- object_storage_delete: 删除成功
- object_storage_list: 列举 / prefix 过滤 / limit 边界
- execute 统一入口: 未知 action 返回警告
- executor 路由: TOOL_EXECUTORS 注册验证
- tool_registry: 4 个工具已注册 + schema 生成
- SSRF 防护: 内网 endpoint 拒绝 / 非法协议拒绝
"""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import sys
import types


# ===== boto3 mock(测试环境可能未安装真实 boto3) =====

def _install_boto3_mock():
    """在 sys.modules 注入 boto3 / botocore.config mock,供 _build_client 使用"""
    if "boto3" not in sys.modules:
        boto3_mod = types.ModuleType("boto3")
        boto3_mod.client = MagicMock(return_value=MagicMock())
        sys.modules["boto3"] = boto3_mod
    if "botocore" not in sys.modules:
        botocore_mod = types.ModuleType("botocore")
        config_mod = types.ModuleType("botocore.config")
        config_mod.Config = MagicMock()
        botocore_mod.config = config_mod
        sys.modules["botocore"] = botocore_mod
        sys.modules["botocore.config"] = config_mod


# 合法的公网测试 endpoint(DNS 解析为公网 IP)
_PUBLIC_ENDPOINT = "https://s3.example.com"
# 内网 endpoint(应被 SSRF 拒绝)
_INTERNAL_ENDPOINT = "http://192.168.1.100:9000"
# 非法协议
_FTP_ENDPOINT = "ftp://s3.example.com"


@pytest.fixture
def s3_config(monkeypatch):
    """注入 S3 配置(公网 endpoint)"""
    monkeypatch.setenv("S3_ENDPOINT_URL", _PUBLIC_ENDPOINT)
    monkeypatch.setenv("S3_ACCESS_KEY", "test_ak")
    monkeypatch.setenv("S3_SECRET_KEY", "test_sk")
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_REGION", "us-east-1")
    _install_boto3_mock()


@pytest.fixture
def mock_s3_client(s3_config):
    """构造 mock S3 client,返回 put/get/delete/list 的可配置 mock"""
    client = MagicMock()
    # head_bucket 模拟存在
    client.head_bucket.return_value = {}
    client.create_bucket.return_value = {}
    client.put_object.return_value = {}
    client.delete_object.return_value = {}
    # get_object 返回 StreamingBody mock
    body = MagicMock()
    body.read.return_value = b"hello world"
    client.get_object.return_value = {"Body": body}
    # list_objects_v2 返回 2 个 object
    client.list_objects_v2.return_value = {
        "Contents": [
            {"Key": "reports/a.json", "Size": 100, "LastModified": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            {"Key": "reports/b.json", "Size": 200, "LastModified": datetime(2026, 1, 2, tzinfo=timezone.utc)},
        ],
        "IsTruncated": False,
    }
    # mock SSRF 校验(避免对 s3.example.com 做真实 DNS)
    with patch("tools.object_storage._build_client", return_value=client), \
         patch("tools.object_storage.validate_url_sync", return_value="203.0.113.1"):
        yield client


# ============ object_storage_upload 测试 ============

@pytest.mark.asyncio
async def test_upload_success(mock_s3_client):
    """上传成功:返回 success=True + key + size"""
    from tools.object_storage import execute_upload

    result = await execute_upload(
        {"key": "reports/test.json", "content": "hello world", "content_type": "text/plain"},
        context=None,
    )

    assert result["success"] is True
    assert result["operation"] == "upload"
    assert result["bucket"] == "test-bucket"
    assert result["key"] == "reports/test.json"
    assert result["size"] == len("hello world")
    mock_s3_client.put_object.assert_called_once()
    call_kwargs = mock_s3_client.put_object.call_args
    assert call_kwargs.kwargs["Bucket"] == "test-bucket"
    assert call_kwargs.kwargs["Key"] == "reports/test.json"
    assert call_kwargs.kwargs["Body"] == b"hello world"
    assert call_kwargs.kwargs["ContentType"] == "text/plain"


@pytest.mark.asyncio
async def test_upload_normalizes_leading_slash(mock_s3_client):
    """key 前导 / 被自动去除(S3 key 不能以 / 开头)"""
    from tools.object_storage import execute_upload

    result = await execute_upload(
        {"key": "/reports/test.json", "content": "data"},
        context=None,
    )

    assert result["success"] is True
    assert result["key"] == "reports/test.json"
    mock_s3_client.put_object.assert_called_once()
    assert mock_s3_client.put_object.call_args.kwargs["Key"] == "reports/test.json"


@pytest.mark.asyncio
async def test_upload_dict_content_serialized_as_json(mock_s3_client):
    """dict/list content 自动转 JSON 文本"""
    from tools.object_storage import execute_upload

    payload = {"name": "test", "value": 42}
    result = await execute_upload(
        {"key": "data.json", "content": payload, "content_type": "application/json"},
        context=None,
    )

    assert result["success"] is True
    body = mock_s3_client.put_object.call_args.kwargs["Body"]
    import json
    assert json.loads(body) == payload


@pytest.mark.asyncio
async def test_upload_empty_key_returns_warning(s3_config):
    """空 key 返回 warning(不调用 S3)"""
    from tools.object_storage import execute_upload

    result = await execute_upload({"key": "", "content": "x"}, context=None)
    assert result["success"] is False
    assert "warning" in result


@pytest.mark.asyncio
async def test_upload_empty_content_returns_warning(mock_s3_client):
    """空 content 返回 warning(不调用 S3)"""
    from tools.object_storage import execute_upload

    result = await execute_upload({"key": "k.json", "content": ""}, context=None)
    assert result["success"] is False
    assert "warning" in result
    mock_s3_client.put_object.assert_not_called()


@pytest.mark.asyncio
async def test_upload_ssrf_rejects_internal_endpoint(monkeypatch):
    """SSRF 防护:内网 endpoint 拒绝"""
    monkeypatch.setenv("S3_ENDPOINT_URL", _INTERNAL_ENDPOINT)
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "b")
    _install_boto3_mock()

    from tools.object_storage import execute_upload

    result = await execute_upload({"key": "k", "content": "x"}, context=None)
    assert result["success"] is False
    assert "SSRF" in result["warning"] or "内网" in result["warning"]


@pytest.mark.asyncio
async def test_upload_invalid_protocol_rejected(monkeypatch):
    """非 http/https 协议拒绝"""
    monkeypatch.setenv("S3_ENDPOINT_URL", _FTP_ENDPOINT)
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "b")
    _install_boto3_mock()

    from tools.object_storage import execute_upload

    result = await execute_upload({"key": "k", "content": "x"}, context=None)
    assert result["success"] is False
    assert "协议" in result["warning"]


@pytest.mark.asyncio
async def test_upload_missing_endpoint(monkeypatch):
    """endpoint 未配置返回 warning(不调用 S3)"""
    monkeypatch.delenv("S3_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_BUCKET", "b")
    _install_boto3_mock()

    from tools.object_storage import execute_upload

    result = await execute_upload({"key": "k", "content": "x"}, context=None)
    assert result["success"] is False
    assert "S3_ENDPOINT_URL" in result["warning"] or "未配置" in result["warning"]


@pytest.mark.asyncio
async def test_upload_missing_bucket(monkeypatch):
    """bucket 未配置返回 warning"""
    monkeypatch.setenv("S3_ENDPOINT_URL", _PUBLIC_ENDPOINT)
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.delenv("S3_BUCKET", raising=False)
    _install_boto3_mock()

    from tools.object_storage import execute_upload

    # mock SSRF 校验(避免对 s3.example.com 做真实 DNS)
    with patch("tools.object_storage.validate_url_sync", return_value="203.0.113.1"):
        result = await execute_upload({"key": "k", "content": "x"}, context=None)
    assert result["success"] is False
    assert "S3_BUCKET" in result["warning"]


# ============ object_storage_download 测试 ============

@pytest.mark.asyncio
async def test_download_text(mock_s3_client):
    """下载文本:返回 content + encoding=utf-8"""
    from tools.object_storage import execute_download

    result = await execute_download({"key": "test.txt", "encoding": "utf-8"}, context=None)

    assert result["success"] is True
    assert result["operation"] == "download"
    assert result["content"] == "hello world"
    assert result["encoding"] == "utf-8"
    assert result["size"] == len(b"hello world")
    mock_s3_client.get_object.assert_called_once_with(Bucket="test-bucket", Key="test.txt")


@pytest.mark.asyncio
async def test_download_binary_returns_base64(mock_s3_client):
    """encoding=binary 返回 base64 编码"""
    from tools.object_storage import execute_download
    import base64

    result = await execute_download({"key": "blob.bin", "encoding": "binary"}, context=None)

    assert result["success"] is True
    assert result["encoding"] == "binary"
    # base64 解码后应等于原始字节
    decoded = base64.b64decode(result["content"])
    assert decoded == b"hello world"


@pytest.mark.asyncio
async def test_download_normalizes_key(mock_s3_client):
    """key 前导 / 被规范化"""
    from tools.object_storage import execute_download

    await execute_download({"key": "/data/test.txt"}, context=None)
    assert mock_s3_client.get_object.call_args.kwargs["Key"] == "data/test.txt"


@pytest.mark.asyncio
async def test_download_empty_key_returns_warning(s3_config):
    """空 key 返回 warning"""
    from tools.object_storage import execute_download

    result = await execute_download({"key": ""}, context=None)
    assert result["success"] is False
    assert "warning" in result


# ============ object_storage_delete 测试 ============

@pytest.mark.asyncio
async def test_delete_success(mock_s3_client):
    """删除成功"""
    from tools.object_storage import execute_delete

    result = await execute_delete({"key": "old.json"}, context=None)

    assert result["success"] is True
    assert result["operation"] == "delete"
    assert result["key"] == "old.json"
    mock_s3_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="old.json")


@pytest.mark.asyncio
async def test_delete_empty_key_returns_warning(s3_config):
    """空 key 返回 warning"""
    from tools.object_storage import execute_delete

    result = await execute_delete({"key": ""}, context=None)
    assert result["success"] is False
    assert "warning" in result


# ============ object_storage_list 测试 ============

@pytest.mark.asyncio
async def test_list_success(mock_s3_client):
    """列举成功:返回 items 列表"""
    from tools.object_storage import execute_list

    result = await execute_list({"prefix": "reports/", "limit": 50}, context=None)

    assert result["success"] is True
    assert result["operation"] == "list"
    assert result["count"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["key"] == "reports/a.json"
    assert result["items"][0]["size"] == 100
    mock_s3_client.list_objects_v2.assert_called_once()
    call_kwargs = mock_s3_client.list_objects_v2.call_args.kwargs
    assert call_kwargs["Bucket"] == "test-bucket"
    assert call_kwargs["Prefix"] == "reports/"
    assert call_kwargs["MaxKeys"] == 50


@pytest.mark.asyncio
async def test_list_no_prefix(mock_s3_client):
    """无 prefix:不传 Prefix 参数"""
    from tools.object_storage import execute_list

    await execute_list({"prefix": "", "limit": 100}, context=None)

    call_kwargs = mock_s3_client.list_objects_v2.call_args.kwargs
    assert "Prefix" not in call_kwargs


@pytest.mark.asyncio
async def test_list_invalid_limit_falls_back(mock_s3_client):
    """非法 limit 应回退到默认值 100"""
    from tools.object_storage import execute_list

    result = await execute_list({"prefix": "", "limit": "not-a-number"}, context=None)
    assert result["success"] is True
    assert mock_s3_client.list_objects_v2.call_args.kwargs["MaxKeys"] == 100


@pytest.mark.asyncio
async def test_list_limit_capped_at_1000(mock_s3_client):
    """limit 上限 1000"""
    from tools.object_storage import execute_list

    await execute_list({"prefix": "", "limit": 5000}, context=None)
    assert mock_s3_client.list_objects_v2.call_args.kwargs["MaxKeys"] == 1000


# ============ execute 统一入口测试 ============

@pytest.mark.asyncio
async def test_execute_unknown_action_returns_warning(s3_config):
    """未知 action 返回 warning"""
    from tools.object_storage import execute

    result = await execute({"action": "unknown"}, context=None)
    assert result["success"] is False
    assert "未知 action" in result["warning"]


@pytest.mark.asyncio
async def test_execute_dispatches_upload(mock_s3_client):
    """execute(action=upload) 路由到 execute_upload"""
    from tools.object_storage import execute

    result = await execute(
        {"action": "upload", "key": "k.json", "content": "data"},
        context=None,
    )
    assert result["success"] is True
    assert result["operation"] == "upload"
    mock_s3_client.put_object.assert_called_once()


# ============ executor 路由测试 ============

def test_tool_executors_registered():
    """TOOL_EXECUTORS 应包含 4 个对象存储工具"""
    from tools import TOOL_EXECUTORS

    assert "object_storage_upload" in TOOL_EXECUTORS
    assert "object_storage_download" in TOOL_EXECUTORS
    assert "object_storage_delete" in TOOL_EXECUTORS
    assert "object_storage_list" in TOOL_EXECUTORS


@pytest.mark.asyncio
async def test_executor_routes_object_storage_upload(mock_s3_client):
    """TOOL_EXECUTORS 路由 object_storage_upload → execute_upload"""
    from tools import TOOL_EXECUTORS

    executor = TOOL_EXECUTORS["object_storage_upload"]
    result = await executor({"key": "k.json", "content": "data"}, context=None)
    assert result["success"] is True
    assert result["operation"] == "upload"


# ============ tool_registry 注册验证 ============

def test_registry_has_4_object_storage_tools():
    """tool_registry 注册了 4 个对象存储工具"""
    from core.tool_registry import get_tool

    assert get_tool("object_storage_upload") is not None
    assert get_tool("object_storage_download") is not None
    assert get_tool("object_storage_delete") is not None
    assert get_tool("object_storage_list") is not None


def test_registry_tool_metadata():
    """工具元数据正确(分类/图标/必填字段)"""
    from core.tool_registry import get_tool

    upload = get_tool("object_storage_upload")
    assert upload.category == "数据存储"
    assert upload.icon == "☁️"
    assert "key" in upload.required
    assert "content" in upload.required

    download = get_tool("object_storage_download")
    assert "key" in download.required
    assert "content" not in download.required


def test_registry_get_tool_schema_generates_openai_schema():
    """get_tool_schema 生成 OpenAI function schema"""
    from core.tool_registry import get_tool_schema

    schema = get_tool_schema("object_storage_upload")
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "object_storage_upload"
    assert "key" in schema["function"]["parameters"]["properties"]
    assert "content" in schema["function"]["parameters"]["properties"]
    assert "key" in schema["function"]["parameters"]["required"]
