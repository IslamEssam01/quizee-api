from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from schemas.attempt_summary import AttemptSummary
from schemas.base import BaseResponse, PaginatedResponse
from schemas.question import QuestionCreate, QuestionPrivate, QuestionPublic
from schemas.user import UserPrivate, UserPublic
from utils.enums import Visibility
from utils.error_messages import QuizErrors


class QuizAccess(BaseResponse):
    quiz_id: int
    user_id: int
    user: UserPrivate
    granted_at: datetime
    granted_by: int


class QuizCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    visibility: Visibility
    pass_threshold: int = Field(ge=1, le=100)
    questions: list[QuestionCreate] = Field(min_length=1)
    allow_negative_score: bool = Field(default=True)
    grade_tiers: dict[str, int] | None = Field(default=None)

    @model_validator(mode="after")
    def validate_grade_tiers(self):
        if self.grade_tiers:
            if any(len(grade) > 20 for grade in self.grade_tiers.keys()):
                raise ValueError(QuizErrors.INVALID_GRADE_TIER_NAME)
            if not all(
                0 <= threshold <= 100 for threshold in self.grade_tiers.values()
            ):
                raise ValueError(QuizErrors.INVALID_GRADE_TIERS)

        return self


class QuizUpdate(BaseModel):
    title: str | None = Field(min_length=1, max_length=200, default=None)
    description: str | None = Field(min_length=1, default=None)
    visibility: Visibility | None = Field(default=None)
    pass_threshold: int | None = Field(ge=1, le=100, default=None)
    questions: list[QuestionCreate] | None = Field(min_length=1, default=None)
    allow_negative_score: bool | None = Field(default=None)
    grade_tiers: dict[str, int] | None = Field(default=None)

    @model_validator(mode="after")
    def validate_grade_tiers(self):
        if self.grade_tiers:
            if any(len(grade) > 20 for grade in self.grade_tiers.keys()):
                raise ValueError(QuizErrors.INVALID_GRADE_TIER_NAME)
            if not all(
                0 <= threshold <= 100 for threshold in self.grade_tiers.values()
            ):
                raise ValueError(QuizErrors.INVALID_GRADE_TIERS)

        return self


class QuizBaseResponse(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    attempts_count: int = 0
    allow_negative_score: bool = Field(default=True)
    grade_tiers: dict[str, int] | None = Field(default=None)


class QuizPrivate(QuizBaseResponse):
    owner: UserPrivate
    questions: list[QuestionPrivate]
    pass_rate: float = 0.0
    attempts_summary: list[AttemptSummary] = Field(default_factory=list)
    quiz_access: list[QuizAccess] = Field(default_factory=list)


class QuizPublic(QuizBaseResponse):
    owner: UserPublic
    questions: list[QuestionPublic]


class PaginatedQuizPublicResponse(PaginatedResponse):
    quizzes: list[QuizPublic]


class PaginatedQuizPrivateResponse(PaginatedResponse):
    quizzes: list[QuizPrivate]


class UpdateAccessRequest(BaseModel):
    grant_users: list[str] = Field(default_factory=list)
    revoke_users: list[str] = Field(default_factory=list)


class UpdateAccessResponse(BaseResponse):
    quiz_id: int
    granted_user_ids: list[int] = Field(default_factory=list)
    revoked_user_ids: list[int] = Field(default_factory=list)
