from sqlalchemy import BigInteger, Column, Index, Numeric, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpConcept(AuditTimeMixin, Base):
    """
    知识点/概念表（迁移自 Django knowledge_concept）
    """

    __tablename__ = 'kp_concept'
    __table_args__ = (
        UniqueConstraint('subject_id', 'name', name='uk_kp_concept_subject_id_name'),
        {'comment': '知识点/概念表'},
    )

    concept_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='概念ID')
    subject_id = Column(BigInteger, nullable=False, comment='所属学科ID')
    name = Column(String(200), nullable=False, comment='概念名称')
    description = Column(Text, nullable=True, comment='概念描述')
    mastery = Column(Numeric(5, 4), nullable=False, default=0, server_default='0', comment='掌握度(0-1)')


class KpNote(AuditTimeMixin, Base):
    """
    学习笔记表（迁移自 Django knowledge_note）
    """

    __tablename__ = 'kp_note'
    __table_args__ = (
        Index('idx_kp_note_user_id', 'user_id'),
        Index('idx_kp_note_subject_id', 'subject_id'),
        Index('idx_kp_note_concept_id', 'concept_id'),
        {'comment': '学习笔记表'},
    )

    note_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='笔记ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    title = Column(String(255), nullable=False, comment='笔记标题')
    content = Column(Text, nullable=False, comment='笔记内容')
    subject_id = Column(BigInteger, nullable=True, comment='所属学科ID')
    concept_id = Column(BigInteger, nullable=True, comment='关联概念ID')
