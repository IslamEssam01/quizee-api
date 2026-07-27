from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from schemas.quiz import (
    PaginatedQuizResponse,
    QuizCreate,
    QuizPrivate,
    QuizPublic,
    QuizUpdate,
)
from utils.auth import AccessToken, CurrentUser, get_current_user
from utils.enums import Visibility
from utils.error_messages import QuizErrors
from utils.permission import Action, can_user_do
from utils.quizzes import get_quizzes_with_options, sort_quiz_questions

router = APIRouter()


@router.get("", response_model=PaginatedQuizResponse)
async def get_quizzes(
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return await get_quizzes_with_options(
        db=db, skip=skip, limit=limit, visibility=Visibility.PUBLIC
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

    if token:
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

    sort_quiz_questions(quiz.questions)

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

    sort_quiz_questions(new_quiz.questions)

    return new_quiz


@router.patch("/{quiz_id}", response_model=QuizPrivate)
async def update_quiz(
    quiz_id: int, quiz_update: QuizUpdate, current_user: CurrentUser, db: DBSession
):
    result = await db.execute(select(models.Quiz).where(models.Quiz.id == quiz_id))
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if not can_user_do(current_user, Action.EDIT, quiz.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_UPDATE_QUIZ,
        )

    if quiz_update.questions:
        for question in quiz_update.questions:
            if not any(answer.is_correct for answer in question.answers):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=QuizErrors.NO_CORRECT_ANSWER,
                )

    update_data = quiz_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(quiz, key, value)

    await db.commit()
    await db.refresh(quiz, attribute_names=["owner"])

    sort_quiz_questions(quiz.questions)
    return quiz


@router.delete("/{quiz_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quiz(quiz_id: int, current_user: CurrentUser, db: DBSession):
    result = await db.execute(select(models.Quiz).where(models.Quiz.id == quiz_id))
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if not can_user_do(current_user, Action.EDIT, quiz.owner_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_DELETE_QUIZ,
        )

    await db.delete(quiz)
    await db.commit()
