"""日志配置：控制台 + 按日轮转文件持久化 + request_id 注入 + 可选 JSON 格式"""
import os
import logging
import logging.config


# 日志目录与文件路径（backend/logs/flowgenie.log）
_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "flowgenie.log")

# 文本日志格式（含 request_id 占位）
_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(request_id)s] %(name)s: %(message)s"

# JSON 日志格式字段（pythonjsonlogger）
_JSON_FIELDS = [
    "asctime", "levelname", "request_id", "name", "message",
]


class RequestIdFilter(logging.Filter):
    """从 contextvars 读取 request_id 注入到每条 log record。
    未在请求上下文内时填 "-"。
    """
    def filter(self, record: logging.LogRecord) -> bool:
        # 延迟导入避免循环依赖(logging_config 在 main 之前加载)
        from core.request_context import request_id_var
        record.request_id = request_id_var.get() or "-"
        return True


def _build_formatter():
    """根据 LOG_FORMAT_JSON env 开关构建 formatter。
    JSON 依赖缺失时回退到文本格式。
    """
    use_json = os.getenv("LOG_FORMAT_JSON", "").lower() in ("1", "true", "yes")
    if use_json:
        try:
            from pythonjsonlogger import jsonlogger
            return jsonlogger.JsonFormatter(
                fmt=" ".join(f"%({f})s" for f in _JSON_FIELDS),
                rename_fields={"asctime": "ts", "levelname": "level", "name": "logger"},
            )
        except ImportError:
            # python-json-logger 未安装,回退文本格式
            pass
    return logging.Formatter(_LOG_FORMAT)


def setup_logging() -> None:
    """初始化全局日志配置。

    - 控制台输出 INFO 级别
    - 文件输出 DEBUG 级别，按日轮转（midnight），保留 7 天
    - 根 logger 级别 DEBUG
    - 注入 request_id（RequestContextMiddleware 写入 contextvars）
    - LOG_FORMAT_JSON=1 时输出 JSON 结构化日志（生产推荐）
    - uvicorn.access 恢复 INFO,保留 HTTP 请求日志
    - httpx/httpcore 保持 WARNING（请求级噪音过大）
    """
    # 确保日志目录存在
    os.makedirs(_LOG_DIR, exist_ok=True)

    formatter = _build_formatter()
    request_filter = RequestIdFilter()

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": lambda: request_filter,
            },
        },
        "formatters": {
            "default": {
                "()": lambda: formatter,
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "default",
                "filters": ["request_id"],
                "stream": "ext://sys.stdout",
            },
            "file": {
                "class": "logging.handlers.TimedRotatingFileHandler",
                "level": "DEBUG",
                "formatter": "default",
                "filters": ["request_id"],
                "filename": _LOG_FILE,
                "when": "midnight",
                "backupCount": 7,
                "encoding": "utf-8",
                "utc": False,
            },
        },
        "loggers": {
            # 恢复 access log(INFO),保留 HTTP 请求可见性
            "uvicorn": {
                "level": "INFO",
                "propagate": True,
            },
            "uvicorn.access": {
                "level": "INFO",
                "propagate": True,
            },
            "uvicorn.error": {
                "level": "WARNING",
                "propagate": True,
            },
            # httpx/httpcore 请求噪音仍抑制
            "httpx": {
                "level": "WARNING",
                "propagate": True,
            },
            "httpcore": {
                "level": "WARNING",
                "propagate": True,
            },
        },
        "root": {
            "level": "DEBUG",
            "handlers": ["console", "file"],
        },
    })


# 模块导入时自动创建日志目录，便于提前调用
os.makedirs(_LOG_DIR, exist_ok=True)
