from datetime import datetime

from pydantic import BaseModel, Field

from schemas.base import BaseResponse, PaginatedResponse
from schemas.user import UserPrivate, UserPublic
from utils.enums import QuestionType, Visibility


class AnswerBase(BaseModel):
    id: int
    text: str = Field(min_length=1)


class AnswerCreate(AnswerBase):
    is_correct: bool


class AnswerPrivate(AnswerBase, BaseResponse):
    is_correct: bool


class AnswerPublic(AnswerBase, BaseResponse):
    pass


class QuestionBase(BaseModel):
    id: int
    text: str = Field(min_length=1)
    type: QuestionType
    position: int = Field(ge=1)
    points: int = Field(ge=1, default=1)


class QuestionCreate(QuestionBase):
    answers: list[AnswerCreate] = Field(min_length=2)


class QuestionPrivate(QuestionBase, BaseResponse):
    answers: list[AnswerPrivate]


class QuestionPublic(QuestionBase, BaseResponse):
    answers: list[AnswerPublic]


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    visibility: Visibility
    pass_threshold: int = Field(ge=1, le=100)
    questions: list[QuestionCreate] = Field(min_length=1)


class QuizUpdate(BaseModel):
    title: str | None = Field(min_length=1, max_length=200, default=None)
    description: str | None = Field(min_length=1, default=None)
    visibility: Visibility | None = Field(default=None)
    pass_threshold: int | None = Field(ge=1, le=100, default=None)
    questions: list[QuestionCreate] | None = Field(min_length=1, default=None)


class QuizAttempt(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    questions: list[QuestionPrivate]


class AttemptSummary(BaseResponse):
    id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime | None
    score: float | None
    passed: bool | None


class QuizPrivate(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    owner: UserPrivate
    questions: list[QuestionPrivate]
    attempts_count: int = 0
    pass_rate: float = 0.0
    attempts_summary: list[AttemptSummary] = Field(default_factory=list)


class QuizPublic(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    owner: UserPublic
    questions: list[QuestionPublic]
    attempts_count: int = 0


class PaginatedQuizPublicResponse(PaginatedResponse):
    quizzes: list[QuizPublic]


class PaginatedQuizPrivateResponse(PaginatedResponse):
    quizzes: list[QuizPrivate]


class StartAttemptRequest(BaseModel):
    taker_name: str | None = Field(default=None)


class StartAttemptResponse(BaseResponse):
    id: int
    quiz: QuizPublic


class AttemptAnswer(BaseModel):
    question_id: int
    answer_id: int


class SubmitAttemptRequest(BaseModel):
    answers: list[AttemptAnswer]


class SubmitAttemptResponse(BaseResponse):
    id: int
    quiz_id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime
    quiz_json: QuizAttempt
    answers_json: list[AttemptAnswer] | None
    score: int
    passed: bool
