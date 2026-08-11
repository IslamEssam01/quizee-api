from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from schemas.base import BaseResponse, PaginatedResponse
from schemas.user import UserPrivate, UserPublic
from utils.enums import GradingMode, QuestionType, Visibility
from utils.error_messages import QuizErrors


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


class QuizAttemptBase(BaseResponse):
    id: int
    title: str
    description: str
    visibility: Visibility
    pass_threshold: int
    owner_id: int
    allow_negative_score: bool = Field(default=True)
    grade_tiers: dict[str, int] | None = Field(default=None)


class PublicQuizAttempt(QuizAttemptBase):
    questions: list[QuestionPublic]


class PrivateQuizAttempt(QuizAttemptBase):
    questions: list[QuestionPrivate]


class AttemptSummary(BaseResponse):
    id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime | None
    score: float | None
    passed: bool | None


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


class QuizAccess(BaseResponse):
    quiz_id: int
    user_id: int
    user: UserPrivate
    granted_at: datetime
    granted_by: int


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


class StartAttemptRequest(BaseModel):
    taker_name: str | None = Field(default=None)


class AttemptResponse(BaseResponse):
    id: int
    quiz: PublicQuizAttempt


class AttemptAnswer(BaseModel):
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
    answers: list[AttemptAnswer]


class UpdateAttemptResponse(BaseResponse):
    id: int
    quiz_id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    quiz_json: PublicQuizAttempt
    answers_json: list[AttemptAnswer] | None


class UserAttempt(BaseResponse):
    id: int
    quiz_id: int
    user_id: int
    started_at: datetime
    taken_at: datetime | None
    quiz_json: PrivateQuizAttempt | None
    answers_json: list[AttemptAnswer] | None
    score: float | None
    passed: bool | None

    @model_validator(mode="after")
    def validate_quiz_json(self):
        if not self.taken_at:
            self.quiz_json = None

        return self


class PaginatedUserAttemptResponse(PaginatedResponse):
    attempts: list[UserAttempt]


class SubmitAttemptResponse(BaseResponse):
    id: int
    quiz_id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime
    quiz_json: PrivateQuizAttempt
    answers_json: list[AttemptAnswer] | None
    score: float
    passed: bool
    grade: str | None = Field(default=None)


class UpdateAccessRequest(BaseModel):
    grant_users: list[str] = Field(default_factory=list)
    revoke_users: list[str] = Field(default_factory=list)


class UpdateAccessResponse(BaseResponse):
    quiz_id: int
    granted_user_ids: list[int] = Field(default_factory=list)
    revoked_user_ids: list[int] = Field(default_factory=list)
