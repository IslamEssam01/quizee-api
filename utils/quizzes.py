from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from schemas.quiz import PaginatedQuizResponse, QuestionPrivate, QuizPublic
from utils.enums import Visibility


def sort_quiz_questions(questions: list[QuestionPrivate]):
    questions.sort(key=lambda question: question["position"])


async def get_quizzes_with_options(
    db: DBSession,
    skip: int,
    limit: int,
    owner_id: int | None = None,
    visibility: Visibility | None = None,
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

    return PaginatedQuizResponse(
        quizzes=[QuizPublic.model_validate(quiz) for quiz in quizzes],
        skip=skip,
        limit=limit,
        total=total,
        has_more=has_more,
    )
