from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from schemas.base import BaseResponse, PaginatedResponse
from schemas.question import QuestionPrivate, QuestionPublic
from schemas.quiz import QuizBaseResponse
from utils.error_messages import QuizErrors


class AttemptQuizPublic(QuizBaseResponse):
    questions: list[QuestionPublic]


class AttemptQuizPrivate(QuizBaseResponse):
    questions: list[QuestionPrivate]


class StartAttemptRequest(BaseModel):
    taker_name: str | None = Field(default=None)


class AttemptResponse(BaseResponse):
    id: int
    quiz: AttemptQuizPublic


class SubmitAttemptAnswer(BaseModel):
    question_id: int
    answer_id: int | None = Field(default=None)
    answer_ids: list[int] | None = Field(default=None)

    @model_validator(mode="after")
    def verify_answer_fields(self):
        answer_id = self.answer_id
        answer_ids = self.answer_ids

        if answer_id is not None and answer_ids is not None:
            raise ValueError(QuizErrors.INVALID_ANSWER_FIELDS)

        if answer_id is None and answer_ids is None:
            raise ValueError(QuizErrors.MISSING_ANSWER_FIELDS)

        return self


class SubmitAttemptRequest(BaseModel):
    answers: list[SubmitAttemptAnswer]


class SubmitAttemptResponse(BaseResponse):
    id: int
    quiz_id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime
    quiz_json: AttemptQuizPrivate
    answers_json: list[SubmitAttemptAnswer] | None
    score: float
    passed: bool
    grade: str | None = Field(default=None)


class UpdateAttemptResponse(BaseResponse):
    id: int
    quiz_id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    quiz_json: AttemptQuizPublic
    answers_json: list[SubmitAttemptAnswer] | None


class UserAttempt(BaseResponse):
    id: int
    quiz_id: int
    user_id: int
    started_at: datetime
    taken_at: datetime | None
    quiz_json: AttemptQuizPrivate | None
    answers_json: list[SubmitAttemptAnswer] | None
    score: float | None
    passed: bool | None
    grade: str | None = Field(default=None)

    @model_validator(mode="after")
    def validate_quiz_json(self):
        if not self.taken_at:
            self.quiz_json = None

        return self


class PaginatedUserAttemptResponse(PaginatedResponse):
    attempts: list[UserAttempt]
