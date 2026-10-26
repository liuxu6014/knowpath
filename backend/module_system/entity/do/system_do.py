from sqlalchemy import JSON, BigInteger, Boolean, Column, Index, Integer, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpAuditLog(AuditTimeMixin, Base):
    """
    审计日志表（迁移自 Django system_auditlog）
    """

    __tablename__ = 'kp_audit_log'
    __table_args__ = (
        Index('idx_kp_audit_log_user_id', 'user_id'),
        {'comment': '审计日志表'},
    )

    log_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='日志ID')
    user_id = Column(BigInteger, nullable=True, comment='用户ID')
    action = Column(String(80), nullable=False, comment='操作动作')
    path = Column(String(255), nullable=True, comment='请求路径')
    detail = Column(JSON, nullable=True, default=dict, comment='详情')


class KpTaskRecord(AuditTimeMixin, Base):
    """
    异步任务记录表（迁移自 Django system_taskrecord）
    """

    __tablename__ = 'kp_task_record'
    __table_args__ = {'comment': '异步任务记录表'}

    task_record_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务记录ID')
    name = Column(String(120), nullable=False, comment='任务名称')
    status = Column(String(30), nullable=False, default='queued', server_default='queued', comment='状态')
    result = Column(JSON, nullable=True, default=dict, comment='结果')


class KpModelConfig(AuditTimeMixin, Base):
    """
    模型配置表（迁移自 Django system_modelconfig）
    """

    __tablename__ = 'kp_model_config'
    __table_args__ = (
        UniqueConstraint('name', name='uk_kp_model_config_name'),
        {'comment': '模型配置表'},
    )

    config_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='配置ID')
    name = Column(String(120), nullable=False, comment='配置名称')
    provider = Column(String(80), nullable=False, default='openai-compatible', server_default='openai-compatible', comment='提供方')
    base_url = Column(String(200), nullable=True, comment='基础URL')
    model = Column(String(120), nullable=True, comment='模型名')
    enabled = Column(Boolean, nullable=False, default=True, server_default='1', comment='是否启用')


class KpPromptTemplate(AuditTimeMixin, Base):
    """
    提示词模板表（迁移自 Django system_prompttemplate）
    """

    __tablename__ = 'kp_prompt_template'
    __table_args__ = (
        UniqueConstraint('code', 'version', name='uk_kp_prompt_template_code_version'),
        {'comment': '提示词模板表'},
    )

    template_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='模板ID')
    code = Column(String(120), nullable=False, comment='模板编码')
    version = Column(Integer, nullable=False, default=1, server_default='1', comment='版本号')
    template = Column(Text, nullable=False, comment='模板内容')
    enabled = Column(Boolean, nullable=False, default=True, server_default='1', comment='是否启用')
