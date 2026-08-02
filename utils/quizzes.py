from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from schemas.quiz import (
    AttemptAnswer,
    PaginatedQuizPrivateResponse,
    PaginatedQuizPublicResponse,
    QuestionCreate,
    QuestionPrivate,
    QuizAttempt,
    QuizPrivate,
    QuizPublic,
)
from utils.enums import GradingMode, Visibility
from utils.error_messages import QuizErrors


def sort_quiz_questions(questions: list[dict[str, Any]]):
    questions.sort(key=lambda question: question["position"])


async def get_attempts_count(db: DBSession, quiz_id: int) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(models.Attempt)
        .where(models.Attempt.quiz_id == quiz_id)
    )
    return result.scalar() or 0


async def get_attempts_count_map(db: DBSession, quiz_ids: list[int]) -> dict[int, int]:
    if not quiz_ids:
        return {}

    result = await db.execute(
        select(models.Attempt.quiz_id, func.count())
        .where(models.Attempt.quiz_id.in_(quiz_ids))
        .group_by(models.Attempt.quiz_id)
    )
    return dict(result.all())


async def get_quiz_attempts(db: DBSession, quiz_id: int) -> list["models.Attempt"]:
    result = await db.execute(
        select(models.Attempt)
        .where(models.Attempt.quiz_id == quiz_id)
        .order_by(models.Attempt.started_at.desc())
    )
    return list(result.scalars().all())


def calculate_pass_rate(attempts: list["models.Attempt"]) -> float:
    submitted = [attempt for attempt in attempts if attempt.taken_at is not None]
    if not submitted:
        return 0.0

    passed = sum(1 for attempt in submitted if attempt.passed)
    return (passed / len(submitted)) * 100


def validate_quiz_questions(questions: list[QuestionCreate]):
    question_ids: set[int] = set()
    for question in questions:
        if question.id in question_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=QuizErrors.DUPLICATE_QUESTION,
            )
        question_ids.add(question.id)

        answer_ids: set[int] = set()
        for answer in question.answers:
            if answer.id in answer_ids:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=QuizErrors.DUPLICATE_ANSWER,
                )
            answer_ids.add(answer.id)

        if not any(answer.is_correct for answer in question.answers):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=QuizErrors.NO_CORRECT_ANSWER,
            )


async def get_quizzes_with_options(
    db: DBSession,
    skip: int,
    limit: int,
    owner_id: int | None = None,
    visibility: Visibility | None = None,
    is_public: bool = True,
):
    where_filters: list[ColumnElement[bool]] = []
    if visibility:
        where_filters.append(models.Quiz.visibility == visibility)
    if owner_id:
        where_filters.append(models.Quiz.owner_id == owner_id)

    count_result = await db.execute(
        select(func.count()).select_from(models.Quiz).where(*where_filters)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
        )
        .where(*where_filters)
        .order_by(models.Quiz.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    quizzes = result.scalars().all()
    for quiz in quizzes:
        sort_quiz_questions(quiz.questions)

    has_more = skip + len(quizzes) < total
    attempts_count_map = await get_attempts_count_map(db, [quiz.id for quiz in quizzes])

    if is_public:
        return PaginatedQuizPublicResponse(
            quizzes=[
                QuizPublic.model_validate(quiz).model_copy(
                    update={"attempts_count": attempts_count_map.get(quiz.id, 0)}
                )
                for quiz in quizzes
            ],
            skip=skip,
            limit=limit,
            total=total,
            has_more=has_more,
        )

    return PaginatedQuizPrivateResponse(
        quizzes=[
            QuizPrivate.model_validate(quiz).model_copy(
                update={"attempts_count": attempts_count_map.get(quiz.id, 0)}
            )
            for quiz in quizzes
        ],
        skip=skip,
        limit=limit,
        total=total,
        has_more=has_more,
    )


def calculate_score(
    questions: list[QuestionPrivate],
    answers: list[AttemptAnswer],
    allow_negative_score: bool = True,
):
    score = 0
    for answer in answers:
        answer_ids = [answer.answer_id] if answer.answer_id else answer.answer_ids or []
        question = next(
            (question for question in questions if question.id == answer.question_id),
            None,
        )
        if not question:
            continue
        correct_answers = [answer for answer in question.answers if answer.is_correct]
        if not correct_answers:
            continue
        wrong_answers_count = len(
            set(answer_ids) - set(answer.id for answer in correct_answers)
        )
        if question.grading_mode is GradingMode.ALL_OR_NOTHING:
            if answer_ids and set(answer_ids) == set(
                answer.id for answer in correct_answers
            ):
                score += question.points
        elif (
            question.grading_mode is GradingMode.PARTIAL_CREDIT
            and wrong_answers_count == 0
        ):
            correct_answers_have_points = any(
                answer.points is not None for answer in correct_answers
            )
            if correct_answers_have_points:
                score += sum(
                    answer.points or 0
                    for answer in correct_answers
                    if answer.id in answer_ids
                )
            else:
                correct_count = len(
                    set(answer_ids) & set(answer.id for answer in correct_answers)
                )
                score += (correct_count / len(correct_answers)) * question.points
        score -= wrong_answers_count * question.penalty_per_wrong

    if not allow_negative_score:
        score = max(score, 0)
    return score


def is_attempt_passed(quiz: QuizAttempt, score: float):
    total = sum(question.points for question in quiz.questions)

    return (score / total) * 100 >= quiz.pass_threshold
