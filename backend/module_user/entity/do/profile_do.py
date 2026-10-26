from sqlalchemy import JSON, BigInteger, Column, String, Text, UniqueConstraint

from common.mixin import AuditTimeMixin
from config.database import Base


class KpProfile(AuditTimeMixin, Base):
    """
    用户学习画像表（迁移自 Django users_profile）

    与 RuoYi sys_user 一对一，通过 user_id 关联；不修改框架表结构。
    """

    __tablename__ = 'kp_profile'
    __table_args__ = (
        UniqueConstraint('user_id', name='uk_kp_profile_user_id'),
        {'comment': '用户学习画像表'},
    )

    profile_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='画像ID')
    user_id = Column(BigInteger, nullable=False, comment='用户ID')
    avatar = Column(String(200), nullable=True, comment='头像URL')
    major = Column(String(120), nullable=True, comment='专业')
    level = Column(String(40), nullable=True, comment='年级/水平')
    goals = Column(Text, nullable=True, comment='学习目标')
    preferences = Column(JSON, nullable=True, default=dict, comment='偏好设置')
