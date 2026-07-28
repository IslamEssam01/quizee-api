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
from utils.enums import Visibility
from utils.error_messages import QuizErrors


def sort_quiz_questions(questions: list[dict[str, Any]]):
    questions.sort(key=lambda question: question["position"])


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

    if is_public:
        return PaginatedQuizPublicResponse(
            quizzes=[QuizPublic.model_validate(quiz) for quiz in quizzes],
            skip=skip,
            limit=limit,
            total=total,
            has_more=has_more,
        )

    return PaginatedQuizPrivateResponse(
        quizzes=[QuizPrivate.model_validate(quiz) for quiz in quizzes],
        skip=skip,
        limit=limit,
        total=total,
        has_more=has_more,
    )


def calculate_score(questions: list[QuestionPrivate], answers: list[AttemptAnswer]):
    score = 0
    for answer in answers:
        question = next(
            (question for question in questions if question.id == answer.question_id),
            None,
        )
        if not question:
            continue
        correct_answer = next(
            (answer for answer in question.answers if answer.is_correct), None
        )
        if not correct_answer:
            continue
        if correct_answer.id == answer.answer_id:
            score += 1

    return score


def is_attempt_passed(quiz: QuizAttempt, score: float):
    total = len(quiz.questions)

    return (score / total) * 100 >= quiz.pass_threshold
