from pydantic import BaseModel, Field

from schemas.base import BaseResponse, PaginatedResponse
from schemas.user import UserPrivate, UserPublic
from utils.enums import QuestionType, Visibility


class AnswerCreate(BaseModel):
    id: int
    text: str = Field(min_length=1)
    is_correct: bool


class AnswerPrivate(BaseResponse):
    id: int
    text: str
    is_correct: bool


class AnswerPublic(BaseResponse):
    id: int
    text: str


class QuestionCreate(BaseModel):
    id: int
    text: str = Field(min_length=1)
    type: QuestionType
    position: int = Field(ge=1)
    answers: list[AnswerCreate] = Field(min_length=2)


class QuestionPrivate(BaseResponse):
    id: int
    text: str
    type: QuestionType
    position: int
    answers: list[AnswerPrivate]


class QuestionPublic(BaseResponse):
    id: int
    text: str
    type: QuestionType
    position: int
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


class QuizPrivate(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    owner: UserPrivate
    questions: list[QuestionPrivate]


class QuizPublic(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    owner: UserPublic
    questions: list[QuestionPublic]


class PaginatedQuizPublicResponse(PaginatedResponse):
    quizzes: list[QuizPublic]


class PaginatedQuizPrivateResponse(PaginatedResponse):
    quizzes: list[QuizPrivate]


class StartAttemptRequest(BaseModel):
    taker_name: str | None = Field(default=None)


class StartAttemptResponse(BaseResponse):
    id: int
    quiz: QuizPublic
