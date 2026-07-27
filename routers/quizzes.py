from hmac import new
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from schemas.quiz import PaginatedQuizResponse, QuizCreate, QuizPrivate, QuizPublic
from utils.auth import AccessToken, CurrentUser, get_current_user
from utils.enums import Visibility
from utils.error_messages import QuizErrors
from utils.permission import Action, can_user_do

router = APIRouter()


@router.get("", response_model=PaginatedQuizResponse)
async def get_quizzes(
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    count_result = await db.execute(
        select(func.count())
        .select_from(models.Quiz)
        .where(models.Quiz.visibility == Visibility.PUBLIC)
    )
    total = count_result.scalar() or 0

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
        )
        .where(models.Quiz.visibility == Visibility.PUBLIC)
        .order_by(models.Quiz.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    quizzes = result.scalars().all()

    for quiz in quizzes:
        quiz.questions.sort(key= lambda question: question["position"])

    has_more = skip + len(quizzes) < total

    return PaginatedQuizResponse(
        quizzes=[QuizPublic.model_validate(quiz) for quiz in quizzes],
        skip=skip,
        limit=limit,
        total=total,
        has_more=has_more,
    )


@router.get("/{quiz_id}", response_model=QuizPublic)
async def get_quiz(
    quiz_id: int,
    db: DBSession,
    token: AccessToken | None = None,
):
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
        )
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    user: models.User | None = None

    try:
        user = await get_current_user(token, db)
    except:
        pass

    if quiz.visibility != Visibility.PUBLIC and (
        not user or not can_user_do(user, Action.VIEW, quiz.owner_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_VIEW_QUIZ,
        )

    quiz.questions.sort(key=lambda question: question["position"])

    return quiz


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuizPrivate)
async def create_quiz(quiz: QuizCreate, current_user: CurrentUser, db: DBSession):
    for question in quiz.questions:
        if not any(answer.is_correct for answer in question.answers):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=QuizErrors.NO_CORRECT_ANSWER,
            )

    new_quiz = models.Quiz(
        title=quiz.title,
        description=quiz.description,
        visibility=quiz.visibility,
        pass_threshold=quiz.pass_threshold,
        owner_id=current_user.id,
        questions=[question.model_dump(mode="json") for question in quiz.questions],
    )

    db.add(new_quiz)

    await db.commit()
    await db.refresh(new_quiz, attribute_names=["owner"])

    new_quiz.questions.sort(key=lambda question: question["position"])

    return new_quiz
