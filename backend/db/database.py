"""SQLite 数据库连接与会话管理"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# 数据库文件路径（放在 backend 目录下）
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "flowgenie.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
    pool_size=5,
    max_overflow=0,
    pool_timeout=30,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    """每个新连接建立时设置 SQLite PRAGMA。

    - journal_mode=WAL：写前日志（Write-Ahead Logging），提升并发读写性能
    - synchronous=NORMAL：WAL 模式下推荐设置，兼顾性能与数据安全
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """FastAPI 依赖：提供数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库表（应用启动时调用）"""
    from db import models  # noqa: F401  确保模型被导入
    Base.metadata.create_all(bind=engine)
    _migrate_run_records_logs()
    _migrate_run_records_trigger_data()
    _migrate_workflows_tags()
    _migrate_workflows_webhook_secret()
    _migrate_run_records_token_usage()
    _migrate_run_records_status_started_at_index()
    _migrate_run_records_paused_fields()
    _migrate_workflows_on_complete_trigger()


def _migrate_run_records_status_started_at_index():
    """P2: 轻量级迁移——为 run_records 表补充复合索引 (status, started_at)。

    Base.metadata.create_all 不会为已存在的表追加索引,此处用
    CREATE INDEX IF NOT EXISTS 显式补建,加速 dashboard 聚合查询。
    复合索引顺序(status, started_at)适合 WHERE status IN (...) AND started_at >= ?
    类的过滤,覆盖趋势/总览/失败聚类等查询路径。
    """
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_run_records_status_started_at "
            "ON run_records (status, started_at)"
        )
        conn.commit()


def _migrate_run_records_logs():
    """轻量级迁移：为已存在的 run_records 表补充 logs 列。

    SQLAlchemy 的 create_all 只创建不存在的表，不会向已有表追加新列。
    此处通过 PRAGMA table_info 检测并 ALTER TABLE 补列，保证旧库升级。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(run_records)").fetchall()
        col_names = {row[1] for row in cols}
        if "logs" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN logs TEXT")
            conn.commit()


def _migrate_run_records_trigger_data():
    """轻量级迁移：为已存在的 run_records 表补充 trigger_data 列。

    存储触发数据用于重试恢复,与 logs 同模式补列。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(run_records)").fetchall()
        col_names = {row[1] for row in cols}
        if "trigger_data" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN trigger_data TEXT")
            conn.commit()


def _migrate_workflows_tags():
    """轻量级迁移：为已存在的 workflows 表补充 tags 列（JSON 数组字符串）。

    与 _migrate_run_records_logs 同模式：create_all 不会向已有表追加新列，
    通过 PRAGMA table_info 检测并 ALTER TABLE 补列，默认值为 "[]"。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(workflows)").fetchall()
        col_names = {row[1] for row in cols}
        if "tags" not in col_names:
            conn.exec_driver_sql('ALTER TABLE workflows ADD COLUMN tags TEXT DEFAULT "[]"')
            conn.commit()


def _migrate_workflows_webhook_secret():
    """轻量级迁移：为已存在的 workflows 表补充 webhook_secret 列。

    用于 webhook HMAC 签名校验。None=不校验(向后兼容),非 None=必须签名。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(workflows)").fetchall()
        col_names = {row[1] for row in cols}
        if "webhook_secret" not in col_names:
            conn.exec_driver_sql("ALTER TABLE workflows ADD COLUMN webhook_secret VARCHAR(64)")
            conn.commit()


def _migrate_run_records_token_usage():
    """B4: 轻量级迁移——为已存在的 run_records 表补充 token_usage 列。

    存储 LLM token 用量统计(JSON 字符串),与 logs/trigger_data 同模式补列。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(run_records)").fetchall()
        col_names = {row[1] for row in cols}
        if "token_usage" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN token_usage TEXT")
            conn.commit()


def _migrate_run_records_paused_fields():
    """A1: 轻量级迁移——为已存在的 run_records 表补充审批暂停相关列。

    - paused_context: JSON 序列化的 ExecutionContext(已完成步骤输出+变量+日志+token用量)
    - paused_step_id: 触发暂停的 approve_node 步骤 ID
    - paused_at: 暂停开始时间(用于超时清理)
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(run_records)").fetchall()
        col_names = {row[1] for row in cols}
        if "paused_context" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN paused_context TEXT")
            conn.commit()
        if "paused_step_id" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN paused_step_id VARCHAR(64)")
            conn.commit()
        if "paused_at" not in col_names:
            conn.exec_driver_sql("ALTER TABLE run_records ADD COLUMN paused_at DATETIME")
            conn.commit()


def _migrate_workflows_on_complete_trigger():
    """A3: 轻量级迁移——为已存在的 workflows 表补充 on_complete_trigger 列。

    存储链式触发配置 JSON: [{workflow_id, on: "success"|"failed"|"always"}]。
    与 tags/webhook_secret 同模式补列,默认值为 "[]"。
    """
    with engine.connect() as conn:
        cols = conn.exec_driver_sql("PRAGMA table_info(workflows)").fetchall()
        col_names = {row[1] for row in cols}
        if "on_complete_trigger" not in col_names:
            conn.exec_driver_sql('ALTER TABLE workflows ADD COLUMN on_complete_trigger TEXT DEFAULT "[]"')
            conn.commit()
