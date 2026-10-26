from sqlalchemy import BigInteger, Boolean, Column, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpSubject(AuditTimeMixin, Base):
    """
    学科/学习主题表（迁移自 Django subjects_subject）
    """

    __tablename__ = 'kp_subject'
    __table_args__ = (
        UniqueConstraint('user_id', 'name', name='uk_kp_subject_user_id_name'),
        {'comment': '学科/学习主题表'},
    )

    subject_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='学科ID')
    name = Column(String(120), nullable=False, comment='学科名称')
    description = Column(Text, nullable=True, comment='学科描述')
    subject_type = Column(String(20), nullable=False, default='topic', server_default='topic', comment='学科类型(paper/course/tech/topic)')
    learning_goal = Column(Text, nullable=True, comment='学习目标')
    archived = Column(Boolean, nullable=False, default=False, server_default='0', comment='是否归档')
    user_id = Column(BigInteger, nullable=False, comment='所有者用户ID')
