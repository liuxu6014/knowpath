from sqlalchemy import JSON, BigInteger, Column, Index, String

from common.mixin import AuditTimeMixin
from config.database import Base


class KpLearningPath(AuditTimeMixin, Base):
    """
    学习路径表（迁移自 Django learning_learningpath）
    """

    __tablename__ = 'kp_learning_path'
    __table_args__ = (
        Index('idx_kp_learning_path_user_id', 'user_id'),
        Index('idx_kp_learning_path_subject_id', 'subject_id'),
        {'comment': '学习路径表'},
    )

    path_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='路径ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    subject_id = Column(BigInteger, nullable=False, comment='所属学科ID')
    title = Column(String(255), nullable=False, default='学习路径', server_default='学习路径', comment='路径标题')
    nodes = Column(JSON, nullable=True, default=list, comment='路径节点列表')
    status = Column(String(30), nullable=False, default='active', server_default='active', comment='状态')
