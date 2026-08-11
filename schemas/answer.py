from pydantic import BaseModel, Field

from schemas.base import BaseResponse


class AnswerBase(BaseModel):
    id: int
    text: str = Field(min_length=1)
    points: float | None = Field(gt=0, default=None)


class AnswerCreate(AnswerBase):
    is_correct: bool


class AnswerPrivate(AnswerBase, BaseResponse):
    is_correct: bool


class AnswerPublic(AnswerBase, BaseResponse):
    pass
