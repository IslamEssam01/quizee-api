from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

if TYPE_CHECKING:
    from models.quiz import Quiz
    from models.user import User


class QuizAccess(Base):
    __tablename__ = "quiz_access"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    granted_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )

    __table_args__ = (
        UniqueConstraint("quiz_id", "user_id", name="uq_quiz_access_quiz_user"),
    )

    user: Mapped["User"] = relationship(
        back_populates="quiz_access", foreign_keys=[user_id]
    )
    quiz: Mapped["Quiz"] = relationship(
        back_populates="quiz_access", foreign_keys=[quiz_id]
    )
