import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.user import relationship

if TYPE_CHECKING:
    from models.answer_option import AnswerOption
    from models.quiz import Quiz


class QuestionType(enum.Enum):
    MCQ = "mcq"
    TRUE_OR_FALSE = "T or F"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    quiz_id: Mapped[int] = mapped_column(
        ForeignKey("quizzes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[QuestionType] = mapped_column(
        Enum(QuestionType), nullable=False, index=True, default=QuestionType.MCQ
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    answers: Mapped["AnswerOption"] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )
