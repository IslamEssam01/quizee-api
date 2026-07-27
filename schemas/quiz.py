from pydantic import BaseModel, ConfigDict, Field

from models.question import QuestionType
from models.quiz import Visibility
from schemas.base import BaseResponse
from schemas.user import UserPrivate, UserPublic


class AnswerCreate(BaseModel):
    text: str = Field(min_length=1)
    is_correct: bool


class AnswerPrivate(BaseResponse):
    text: str
    is_correct: bool
    question_id: int


class AnswerPublic(BaseResponse):
    text: str
    question_id: int


class QuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    type: QuestionType
    position: int = Field(ge=1)
    answers: list[AnswerCreate] = Field(min_length=2)


class QuestionPrivate(BaseResponse):
    text: str
    type: QuestionType
    position: int
    quiz_id: int
    answers: list[AnswerPrivate]


class QuestionPublic(BaseResponse):
    text: str
    type: QuestionType
    position: int
    quiz_id: int
    answers: list[AnswerPublic]


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    visibility: Visibility
    pass_threshold: int = Field(ge=1, le=100)
    questions: list[QuestionCreate] = Field(min_length=1)


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


class PaginatedQuizResponse(BaseModel):
    quizzes: list[QuizPublic]
    skip: int
    limit: int
    total: int
    has_more: bool
