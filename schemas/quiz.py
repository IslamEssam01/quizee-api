from pydantic import BaseModel, Field

from models.question import QuestionType
from models.quiz import Visibility
from schemas.user import UserPrivate


class AnswerCreate(BaseModel):
    text: str = Field(min_length=1)
    is_correct: bool


class AnswerPrivate(BaseModel):
    text: str
    is_correct: bool
    question_id: int


class QuestionCreate(BaseModel):
    text: str = Field(min_length=1)
    type: QuestionType
    position: int = Field(ge=1)
    answers: list[AnswerCreate] = Field(min_length=2)


class QuestionPrivate(BaseModel):
    text: str
    type: QuestionType
    position: int
    quiz_id: int
    answers: list[AnswerPrivate]


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    visibility: Visibility
    pass_threshold: int = Field(ge=1, le=100)
    questions: list[QuestionCreate] = Field(min_length=1)


class QuizPrivate(BaseModel):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    owner: UserPrivate
    questions: list[QuestionPrivate]
