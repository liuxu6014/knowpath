from sqlalchemy import JSON, BigInteger, Column, Index, Integer, SmallInteger, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpResource(AuditTimeMixin, Base):
    """
    学习资料表（迁移自 Django resources_resource）
    """

    __tablename__ = 'kp_resource'
    __table_args__ = (
        Index('idx_kp_resource_user_id', 'user_id'),
        Index('idx_kp_resource_subject_id', 'subject_id'),
        Index('idx_kp_resource_sha256', 'sha256'),
        {'comment': '学习资料表'},
    )

    resource_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='资料ID')
    user_id = Column(BigInteger, nullable=True, comment='所有者用户ID')
    subject_id = Column(BigInteger, nullable=True, comment='所属学科ID')
    title = Column(String(255), nullable=False, comment='资料标题')
    content = Column(Text, nullable=True, comment='资料正文')
    file = Column(String(255), nullable=True, comment='文件路径')
    sha256 = Column(String(64), nullable=False, default='', server_default="''", comment='内容SHA256摘要')


class KpChunk(AuditTimeMixin, Base):
    """
    资料分块表（迁移自 Django resources_chunk）
    """

    __tablename__ = 'kp_chunk'
    __table_args__ = (
        UniqueConstraint('resource_id', 'seq_no', name='uk_kp_chunk_resource_id_seq_no'),
        {'comment': '资料分块表'},
    )

    chunk_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='分块ID')
    resource_id = Column(BigInteger, nullable=False, comment='所属资料ID')
    seq_no = Column(Integer, nullable=False, comment='分块序号')
    content = Column(Text, nullable=False, comment='分块内容')
    metadata_json = Column(JSON, nullable=True, default=dict, comment='分块元数据')


class KpProcessingTask(AuditTimeMixin, Base):
    """
    资料处理任务表（迁移自 Django resources_processingtask）
    """

    __tablename__ = 'kp_processing_task'
    __table_args__ = (
        Index('idx_kp_processing_task_resource_id', 'resource_id'),
        {'comment': '资料处理任务表'},
    )

    task_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='任务ID')
    resource_id = Column(BigInteger, nullable=False, comment='所属资料ID')
    status = Column(String(16), nullable=False, default='pending', server_default='pending', comment='状态(pending/running/succeeded/failed)')
    progress = Column(SmallInteger, nullable=False, default=0, server_default='0', comment='进度(0-100)')
    attempts = Column(Integer, nullable=False, default=0, server_default='0', comment='重试次数')
    error = Column(Text, nullable=True, comment='错误信息')
