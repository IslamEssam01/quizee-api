from pydantic import BaseModel, Field, model_validator

from schemas.answer import AnswerCreate, AnswerPrivate, AnswerPublic
from schemas.base import BaseResponse
from utils.enums import GradingMode, QuestionType
from utils.error_messages import QuizErrors


class QuestionBase(BaseModel):
    id: int
    text: str = Field(min_length=1)
    type: QuestionType
    position: int = Field(ge=1)
    points: float = Field(gt=0, default=1)
    grading_mode: GradingMode = Field(default=GradingMode.ALL_OR_NOTHING)
    penalty_per_wrong: float = Field(ge=0, default=0)
    allow_multiple_answers: bool = Field(default=False)


class QuestionCreate(QuestionBase):
    answers: list[AnswerCreate] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_answers_points(self):
        total_points = sum(
            answer.points for answer in self.answers if answer.points is not None
        )
        if total_points != 0 and total_points != self.points:
            raise ValueError(QuizErrors.INVALID_QUESTION_POINTS)

        correct_answers_count = sum(1 for answer in self.answers if answer.is_correct)
        if correct_answers_count > 1:
            self.allow_multiple_answers = True

        return self


class QuestionPrivate(QuestionBase, BaseResponse):
    answers: list[AnswerPrivate]


class QuestionPublic(QuestionBase, BaseResponse):
    answers: list[AnswerPublic]
