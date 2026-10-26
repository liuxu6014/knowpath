from sqlalchemy import JSON, BigInteger, Column, Index, Integer

from common.mixin import AuditTimeMixin
from config.database import Base


class KpGraphSnapshot(AuditTimeMixin, Base):
    """
    知识图谱快照表（迁移自 Django system_graphsnapshot）

    快照为只追加历史，始终从最新的可用 DAG 快照中选取，
    见 core/graph/resolver.py:latest_usable_graph。
    """

    __tablename__ = 'kp_graph_snapshot'
    __table_args__ = (
        Index('idx_kp_graph_snapshot_subject_id', 'subject_id'),
        Index('idx_kp_graph_snapshot_user_id', 'user_id'),
        {'comment': '知识图谱快照表'},
    )

    snapshot_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='快照ID')
    subject_id = Column(BigInteger, nullable=False, comment='所属学科ID')
    user_id = Column(BigInteger, nullable=True, comment='创建者用户ID')
    nodes = Column(JSON, nullable=True, default=list, comment='节点列表')
    edges = Column(JSON, nullable=True, default=list, comment='边列表')
    version = Column(Integer, nullable=False, default=1, server_default='1', comment='版本号')
