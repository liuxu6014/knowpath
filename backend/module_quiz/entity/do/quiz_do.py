from sqlalchemy import JSON, BigInteger, Column, Index, String

from common.mixin import AuditTimeMixin
from config.database import Base


class KpQuiz(AuditTimeMixin, Base):
    """
    测验表（迁移自 Django quizzes_quiz）
    """

    __tablename__ = 'kp_quiz'
    __table_args__ = (
        Index('idx_kp_quiz_subject_id', 'subject_id'),
        Index('idx_kp_quiz_assessment_id', 'assessment_id'),
        {'comment': '测验表'},
    )

    quiz_id = Column(BigInteger, primary_key=True, nullable=False, autoincrement=True, comment='测验ID')
    assessment_id = Column(BigInteger, nullable=True, comment='关联测评ID')
    title = Column(String(255), nullable=False, comment='测验标题')
    subject_id = Column(BigInteger, nullable=True, comment='所属学科ID')
    questions = Column(JSON, nullable=True, default=list, comment='题目列表')
