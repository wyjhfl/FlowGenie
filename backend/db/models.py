"""数据模型定义：Workflow 和 RunRecord"""
import uuid
import json
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship
from db.database import Base


def gen_uuid():
    return str(uuid.uuid4())


class Workflow(Base):
    """工作流定义"""
    __tablename__ = "workflows"

    id = Column(String(36), primary_key=True, default=gen_uuid)
    name = Column(String(200), nullable=False)
    scenario = Column(String(100), default="")
    summary = Column(Text, default="")
    steps = Column(Text, default="[]")  # JSON 字符串
    edges = Column(Text, default="[]")  # JSON 字符串
    on_failure = Column(String(20), default="stop")  # stop | continue
    tags = Column(Text, default="[]")  # JSON 数组字符串
    # A3: 完成后链式触发配置 JSON: [{workflow_id, on: "success"|"failed"|"always"}]
    # 工作流执行完成后按 status 过滤,on 匹配则异步触发目标工作流,传递 trigger_data + _chain_depth
    on_complete_trigger = Column(Text, default="[]")
    schedule_enabled = Column(Boolean, default=False)
    webhook_id = Column(String(36), nullable=True)  # Webhook 触发用
    webhook_secret = Column(String(64), nullable=True)  # Webhook HMAC 签名密钥(None=不校验,向后兼容)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    runs = relationship("RunRecord", back_populates="workflow", cascade="all, delete-orphan")
    versions = relationship("WorkflowVersion", back_populates="workflow", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "scenario": self.scenario,
            "summary": self.summary,
            "steps": json.loads(self.steps) if self.steps else [],
            "edges": json.loads(self.edges) if self.edges else [],
            "on_failure": self.on_failure,
            "tags": json.loads(self.tags) if self.tags else [],
            "on_complete_trigger": json.loads(self.on_complete_trigger) if self.on_complete_trigger else [],
            "schedule_enabled": self.schedule_enabled,
            "webhook_id": self.webhook_id,
            "webhook_secret": self.webhook_secret,  # 仅在管理 API 返回明文;触发 API 不返回
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WorkflowVersion(Base):
    """工作流版本快照"""
    __tablename__ = "workflow_versions"
    __table_args__ = (Index("ix_workflow_versions_workflow_id", "workflow_id"),)

    id = Column(String(36), primary_key=True, default=gen_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    version_number = Column(Integer, nullable=False)
    steps = Column(Text, default="[]")
    edges = Column(Text, default="[]")
    summary = Column(Text, default="")
    on_failure = Column(String(20), default="stop")
    tags = Column(Text, default="[]")
    note = Column(Text, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    workflow = relationship("Workflow", back_populates="versions")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "version_number": self.version_number,
            "steps": json.loads(self.steps) if self.steps else [],
            "edges": json.loads(self.edges) if self.edges else [],
            "summary": self.summary,
            "on_failure": self.on_failure,
            "tags": json.loads(self.tags) if self.tags else [],
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RunRecord(Base):
    """执行历史记录"""
    __tablename__ = "run_records"
    __table_args__ = (
        Index("ix_run_records_workflow_id", "workflow_id"),
        # P2: 复合索引——加速 dashboard 按 status + started_at 过滤的聚合查询(趋势/总览)
        Index("ix_run_records_status_started_at", "status", "started_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    workflow_id = Column(String(36), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)
    trigger_type = Column(String(20), default="manual")  # manual | schedule | webhook
    # running | success | failed | partial_success | paused(审批节点暂停)
    status = Column(String(20), default="running")
    total_time_ms = Column(Integer, default=0)
    steps_result = Column(Text, default="{}")  # JSON 字符串
    trigger_data = Column(Text, nullable=True)  # JSON 字符串，存储触发数据用于重试恢复
    started_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime, nullable=True)
    error = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # JSON 字符串，存储执行日志数组
    token_usage = Column(Text, nullable=True)  # B4: JSON 字符串,存储 LLM token 用量统计
    # A1: 审批节点暂停相关——paused_context 序列化 ExecutionContext(已完成步骤输出+变量+日志+token用量)
    # paused_step_id 记录触发暂停的 approve_node 步骤 ID;paused_at 记录暂停开始时间(用于超时清理)
    paused_context = Column(Text, nullable=True)  # JSON 字符串
    paused_step_id = Column(String(64), nullable=True)
    paused_at = Column(DateTime, nullable=True)

    workflow = relationship("Workflow", back_populates="runs")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "trigger_type": self.trigger_type,
            "status": self.status,
            "total_time_ms": self.total_time_ms,
            "steps_result": json.loads(self.steps_result) if self.steps_result else {},
            "trigger_data": json.loads(self.trigger_data) if self.trigger_data else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error": self.error,
            "logs": json.loads(self.logs) if self.logs else [],
            "token_usage": json.loads(self.token_usage) if self.token_usage else None,
            # A1: 审批暂停信息(仅在 paused 状态有值);paused_context 不对外暴露(含中间数据)
            "paused_step_id": self.paused_step_id,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
        }


class UserPreference(Base):
    """用户偏好记忆（用于自动填充工作流参数，如 email、telegram_chat_id 等）"""
    __tablename__ = "user_preferences"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True)  # 如 "email", "telegram_chat_id", "slack_webhook_url"
    value = Column(String)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ConversationSession(Base):
    """F2: 多轮对话会话 - 持久化消息历史以支持跨步骤/跨执行的会话上下文延续

    业务 session_id 可由用户指定(如 "customer_123"),便于跨多次工作流执行延续同一会话。
    过期会话(expires_at < now)由 scheduler 定时清理。
    """
    __tablename__ = "conversation_sessions"
    __table_args__ = (
        # expires_at 索引供清理任务按过期时间扫描;session_id 由 column 级 unique=True 自动建索引
        Index("ix_conversation_sessions_expires_at", "expires_at"),
    )

    id = Column(String(36), primary_key=True, default=gen_uuid)
    # 业务会话 ID:用户可指定(如 "customer_123"),缺省自动生成 UUID;unique=True 自动建索引便于按 ID 查询
    session_id = Column(String(100), unique=True, nullable=False)
    # 持久化的系统提示词(创建会话时设定,后续 continue 沿用)
    system_prompt = Column(Text, default="")
    # 消息历史 JSON 字符串:[{role: "user"|"assistant", content: "..."}, ...]
    messages_json = Column(Text, default="[]")
    # 模型覆盖(空则用默认模型)
    model = Column(String(100), default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    # 过期时间:默认 7 天后,由 scheduler 定时清理
    expires_at = Column(DateTime, nullable=False)

    def get_messages(self) -> list[dict]:
        """解析消息历史为 list[dict]"""
        return json.loads(self.messages_json) if self.messages_json else []

    def set_messages(self, messages: list[dict]):
        """将消息列表序列化为 JSON 字符串存储"""
        self.messages_json = json.dumps(messages, ensure_ascii=False)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "system_prompt": self.system_prompt,
            "messages": self.get_messages(),
            "model": self.model,
            "message_count": len(self.get_messages()),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
