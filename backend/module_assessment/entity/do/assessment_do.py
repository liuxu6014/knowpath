from sqlalchemy import JSON, BigInteger, Column, Index, Integer, Numeric, String, UniqueConstraint

from common.mixin import AuditTimeMixin
from common.types import DbUtcDateTime
from config.database import Base


class KpAssessment(AuditTimeMixin, Base):
    """
    测评表（迁移自 Django assessment_assessment）
    """

    __tablename__ = 'kp_assessment'
    __table_args__ = (
        Index('idx_kp_assessment_subject_id', 'subject_id'),
        {'comment': '测评表'},
    )

    assessment_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='测评ID')
    subject_id = Column(BigInteger, nullable=False, comment='所属学科ID')
    title = Column(String(255), nullable=False, comment='测评标题')
    questions = Column(JSON, nullable=True, default=list, comment='题目列表')


class KpAssessmentAttempt(AuditTimeMixin, Base):
    """
    测评作答记录表（迁移自 Django assessment_assessmentattempt）
    """

    __tablename__ = 'kp_assessment_attempt'
    __table_args__ = (
        Index('idx_kp_assessment_attempt_assessment_id', 'assessment_id'),
        Index('idx_kp_assessment_attempt_user_id', 'user_id'),
        {'comment': '测评作答记录表'},
    )

    attempt_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='作答ID')
    assessment_id = Column(BigInteger, nullable=False, comment='测评ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    answers = Column(JSON, nullable=True, default=dict, comment='作答内容')
    score = Column(Numeric(5, 2), nullable=False, default=0, server_default='0', comment='得分(0-100)')


class KpMasteryRecord(AuditTimeMixin, Base):
    """
    用户概念掌握度当前快照表（迁移自 Django assessment_masteryrecord）
    """

    __tablename__ = 'kp_mastery_record'
    __table_args__ = (
        UniqueConstraint('user_id', 'concept_id', name='uk_kp_mastery_record_user_id_concept_id'),
        Index('idx_kp_mastery_record_concept_id', 'concept_id'),
        {'comment': '用户概念掌握度表'},
    )

    record_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='记录ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    concept_id = Column(BigInteger, nullable=False, comment='概念ID')
    mastery = Column(Numeric(5, 4), nullable=False, default=0, server_default='0', comment='掌握度(0-1)')
    confidence = Column(Numeric(5, 4), nullable=False, default=0, server_default='0', comment='置信度(0-1)')
    status = Column(String(20), nullable=False, default='unknown', server_default='unknown', comment='状态(unknown/weak/learning/mastered)')
    evidence_count = Column(Integer, nullable=False, default=0, server_default='0', comment='证据数量')
    last_evidence_at = Column(DbUtcDateTime(), nullable=True, comment='最后证据时间')


class KpMasteryHistory(AuditTimeMixin, Base):
    """
    掌握度变化历史表（迁移自 Django assessment_masteryhistory）
    """

    __tablename__ = 'kp_mastery_history'
    __table_args__ = (
        Index('idx_kp_mastery_history_mastery_record_id', 'mastery_record_id'),
        {'comment': '掌握度变化历史表'},
    )

    history_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='历史ID')
    mastery_record_id = Column(BigInteger, nullable=False, comment='掌握度记录ID')
    before_value = Column(Numeric(5, 4), nullable=False, comment='更新前值')
    after_value = Column(Numeric(5, 4), nullable=False, comment='更新后值')
    delta = Column(Numeric(5, 4), nullable=False, comment='变化量')
    reason = Column(String(32), nullable=False, default='diagnostic', server_default='diagnostic', comment='更新原因')
    evidence_type = Column(String(32), nullable=False, default='', server_default="''", comment='证据类型')
    evidence_id = Column(BigInteger, nullable=True, comment='证据ID')
    calculation_detail = Column(JSON, nullable=True, default=dict, comment='计算详情')
