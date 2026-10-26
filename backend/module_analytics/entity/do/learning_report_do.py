from sqlalchemy import JSON, BigInteger, Column, Index, Integer, String, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpLearningReport(AuditTimeMixin, Base):
    """
    学习报告表（迁移自 Django analytics_learningreport）
    """

    __tablename__ = 'kp_learning_report'
    __table_args__ = (
        UniqueConstraint('user_id', 'subject_id', 'version', name='uk_kp_learning_report_user_id_subject_id_version'),
        {'comment': '学习报告表'},
    )

    report_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='报告ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    subject_id = Column(BigInteger, nullable=False, comment='所属学科ID')
    version = Column(Integer, nullable=False, comment='版本号')
    snapshot = Column(JSON, nullable=False, comment='报告快照')


class KpLearningEvent(AuditTimeMixin, Base):
    """
    学习行为事件表（迁移自 Django analytics_learningevent）
    """

    __tablename__ = 'kp_learning_event'
    __table_args__ = (
        Index('idx_kp_learning_event_user_id_subject_id_create_time', 'user_id', 'subject_id', 'create_time'),
        Index('idx_kp_learning_event_user_id_event_type_create_time', 'user_id', 'event_type', 'create_time'),
        Index('idx_kp_learning_event_event_type', 'event_type'),
        Index('idx_kp_learning_event_trace_id', 'trace_id'),
        Index('idx_kp_learning_event_create_time', 'create_time'),
        {'comment': '学习行为事件表'},
    )

    event_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='事件ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    event_type = Column(String(64), nullable=False, comment='事件类型')
    subject_id = Column(BigInteger, nullable=True, comment='所属学科ID')
    concept_id = Column(BigInteger, nullable=True, comment='概念ID')
    duration_sec = Column(Integer, nullable=False, default=0, server_default='0', comment='时长(秒)')
    metadata_json = Column(JSON, nullable=True, default=dict, comment='事件元数据')
    trace_id = Column(String(64), nullable=True, comment='追踪ID')
