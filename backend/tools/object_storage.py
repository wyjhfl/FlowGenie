"""C1: 对象存储工具(S3 兼容)

支持上传/下载/删除文件到 S3 兼容存储(MinIO / Ceph / AWS S3)。

凭证(从 .env 读取,可通过凭证面板配置):
- S3_ENDPOINT_URL:对象存储服务地址(如 http://minio:9000 或 https://s3.amazonaws.com)
- S3_ACCESS_KEY:访问密钥
- S3_SECRET_KEY:私有密钥
- S3_BUCKET:默认 bucket 名称
- S3_REGION:区域(可选,默认 us-east-1)

安全:
- endpoint_url 必须为 http/https,且禁止指向内网 IP(SSRF 防护)
- 路径分隔符规范化,禁止以 / 开头(S3 key 不能以 / 开头)
"""
import os
import asyncio
import logging
from typing import Any
from urllib.parse import urlparse

from core.ssrf_guard import validate_url_sync

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    """从环境变量读取 S3 配置"""
    return {
        "endpoint_url": os.getenv("S3_ENDPOINT_URL", "").strip(),
        "access_key": os.getenv("S3_ACCESS_KEY", "").strip(),
        "secret_key": os.getenv("S3_SECRET_KEY", "").strip(),
        "bucket": os.getenv("S3_BUCKET", "").strip(),
        "region": os.getenv("S3_REGION", "us-east-1").strip() or "us-east-1",
    }


def _validate_endpoint(endpoint_url: str) -> str:
    """校验 endpoint_url:协议必须 http/https,且禁止指向内网 IP(SSRF 防护)

    :raises ValueError: endpoint 为空 / 协议不允许 / 指向内网
    :return: 校验通过的 endpoint_url
    """
    if not endpoint_url:
        raise ValueError("S3_ENDPOINT_URL 未配置(请在凭证面板配置对象存储服务地址)")
    parsed = urlparse(endpoint_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"S3 endpoint 仅允许 http/https 协议,当前: {parsed.scheme}")
    # 复用 ssrf_guard.validate_url_sync 做内网 IP 拦断(同步解析 DNS)
    # 注:validate_url_sync 会再做一次协议校验,与上面一致
    try:
        validate_url_sync(endpoint_url)
    except ValueError as e:
        raise ValueError(f"S3 endpoint SSRF 校验失败: {e}") from e
    return endpoint_url


def _normalize_key(key: str) -> str:
    """规范化 S3 object key:去除前导 /,去除多余空白"""
    if not key:
        raise ValueError("object key 不能为空")
    key = key.strip().lstrip("/")
    if not key:
        raise ValueError("object key 不能为空")
    return key


def _build_client(config: dict):
    """构造 boto3 S3 客户端(延迟导入,以便未安装 boto3 时模块可加载)"""
    try:
        import boto3  # noqa: F401
        from botocore.config import Config
    except ImportError as e:
        raise RuntimeError(
            "boto3 未安装,请运行: pip install boto3"
        ) from e

    return boto3.client(
        "s3",
        endpoint_url=config["endpoint_url"],
        aws_access_key_id=config["access_key"],
        aws_secret_access_key=config["secret_key"],
        region_name=config["region"],
        config=Config(connect_timeout=10, read_timeout=60, retries={"max_attempts": 3}),
    )


def _ensure_bucket_exists(client, bucket: str) -> None:
    """检查 bucket 是否存在(不存在则尝试创建,简化首次使用流程)"""
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:
        # 不存在则创建(私有访问)
        try:
            client.create_bucket(Bucket=bucket)
            logger.info(f"已自动创建 bucket: {bucket}")
        except Exception as e:
            raise RuntimeError(f"bucket 不存在且创建失败: {bucket} - {e}") from e


# ===== 同步执行逻辑(放线程池执行,避免阻塞事件循环) =====

def _upload_sync(config: dict, key: str, content: str, content_type: str) -> dict:
    """同步上传:将 content 写入 S3 object"""
    _validate_endpoint(config["endpoint_url"])
    client = _build_client(config)
    bucket = config["bucket"]
    if not bucket:
        raise ValueError("S3_BUCKET 未配置")
    _ensure_bucket_exists(client, bucket)

    # content 转 bytes
    if isinstance(content, str):
        body = content.encode("utf-8")
    elif isinstance(content, (bytes, bytearray)):
        body = bytes(content)
    else:
        # dict/list 转 JSON 文本
        import json
        body = json.dumps(content, ensure_ascii=False).encode("utf-8")

    extra_args = {}
    if content_type:
        extra_args["ContentType"] = content_type

    client.put_object(Bucket=bucket, Key=key, Body=body, **extra_args)

    size = len(body)
    return {
        "success": True,
        "operation": "upload",
        "bucket": bucket,
        "key": key,
        "size": size,
        "endpoint": config["endpoint_url"],
    }


def _download_sync(config: dict, key: str, encoding: str) -> dict:
    """同步下载:从 S3 读取 object 内容"""
    _validate_endpoint(config["endpoint_url"])
    client = _build_client(config)
    bucket = config["bucket"]
    if not bucket:
        raise ValueError("S3_BUCKET 未配置")

    response = client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    size = len(body)

    # 按编码返回(text/utf-8 默认;binary 返回 base64)
    if encoding == "binary":
        import base64
        content = base64.b64encode(body).decode("ascii")
        encoding_returned = "binary"
    else:
        # 默认 utf-8 文本
        content = body.decode(encoding or "utf-8", errors="replace")
        encoding_returned = encoding or "utf-8"

    return {
        "success": True,
        "operation": "download",
        "bucket": bucket,
        "key": key,
        "size": size,
        "content": content,
        "encoding": encoding_returned,
    }


def _delete_sync(config: dict, key: str) -> dict:
    """同步删除:S3 object"""
    _validate_endpoint(config["endpoint_url"])
    client = _build_client(config)
    bucket = config["bucket"]
    if not bucket:
        raise ValueError("S3_BUCKET 未配置")

    client.delete_object(Bucket=bucket, Key=key)

    return {
        "success": True,
        "operation": "delete",
        "bucket": bucket,
        "key": key,
    }


def _list_sync(config: dict, prefix: str, limit: int) -> dict:
    """同步列举:返回 bucket 下匹配 prefix 的 object 列表"""
    _validate_endpoint(config["endpoint_url"])
    client = _build_client(config)
    bucket = config["bucket"]
    if not bucket:
        raise ValueError("S3_BUCKET 未配置")

    kwargs = {"Bucket": bucket, "MaxKeys": min(max(limit, 1), 1000)}
    if prefix:
        kwargs["Prefix"] = prefix

    response = client.list_objects_v2(**kwargs)
    items = []
    for obj in response.get("Contents", []):
        items.append({
            "key": obj["Key"],
            "size": obj.get("Size", 0),
            "last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
        })

    return {
        "success": True,
        "operation": "list",
        "bucket": bucket,
        "prefix": prefix,
        "items": items,
        "count": len(items),
        "is_truncated": response.get("IsTruncated", False),
    }


# ===== 异步执行器 =====

async def execute(params: dict, context: Any) -> dict:
    """对象存储工具统一入口(按 action 分派)

    :param params: {action: "upload"|"download"|"delete"|"list", ...}
    :param context: ExecutionContext(暂未使用)
    :return: 操作结果 dict
    """
    action = params.get("action", "")

    if action == "upload":
        return await execute_upload(params, context)
    if action == "download":
        return await execute_download(params, context)
    if action == "delete":
        return await execute_delete(params, context)
    if action == "list":
        return await execute_list(params, context)

    return {
        "success": False,
        "warning": f"未知 action: {action}(支持 upload / download / delete / list)",
    }


async def execute_upload(params: dict, context: Any) -> dict:
    """object_storage_upload:上传文件到 S3"""
    key = params.get("key", "")
    content = params.get("content", "")
    content_type = params.get("content_type", "text/plain")

    try:
        key = _normalize_key(key)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    if not content:
        return {"success": False, "warning": "content 不能为空"}

    config = _get_config()
    try:
        return await asyncio.to_thread(_upload_sync, config, key, content, content_type)
    except Exception as e:
        logger.error(f"object_storage upload 失败: {e}")
        return {"success": False, "warning": f"上传失败: {e}"}


async def execute_download(params: dict, context: Any) -> dict:
    """object_storage_download:从 S3 下载文件内容"""
    key = params.get("key", "")
    encoding = params.get("encoding", "utf-8")

    try:
        key = _normalize_key(key)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    config = _get_config()
    try:
        return await asyncio.to_thread(_download_sync, config, key, encoding)
    except Exception as e:
        logger.error(f"object_storage download 失败: {e}")
        return {"success": False, "warning": f"下载失败: {e}"}


async def execute_delete(params: dict, context: Any) -> dict:
    """object_storage_delete:删除 S3 上的 object"""
    key = params.get("key", "")

    try:
        key = _normalize_key(key)
    except ValueError as e:
        return {"success": False, "warning": str(e)}

    config = _get_config()
    try:
        return await asyncio.to_thread(_delete_sync, config, key)
    except Exception as e:
        logger.error(f"object_storage delete 失败: {e}")
        return {"success": False, "warning": f"删除失败: {e}"}


async def execute_list(params: dict, context: Any) -> dict:
    """object_storage_list:列举 bucket 下的 object"""
    prefix = params.get("prefix", "")
    try:
        limit = int(params.get("limit", 100))
    except (TypeError, ValueError):
        limit = 100

    config = _get_config()
    try:
        return await asyncio.to_thread(_list_sync, config, prefix, limit)
    except Exception as e:
        logger.error(f"object_storage list 失败: {e}")
        return {"success": False, "warning": f"列举失败: {e}"}
