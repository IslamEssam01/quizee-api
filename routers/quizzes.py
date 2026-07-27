from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from models.quiz import Visibility
from schemas.quiz import PaginatedQuizResponse, QuizCreate, QuizPrivate, QuizPublic
from utils.auth import CurrentUser
from utils.error_messages import QuizErrors

router = APIRouter()


@router.get("", response_model=PaginatedQuizResponse)
async def get_quizzes(
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    visibility: Annotated[Visibility, Query()] = Visibility.PUBLIC,
):
    count_reslut = await db.execute(select(func.count()).select_from(models.Quiz))
    total = count_reslut.scalar() or 0

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.questions).selectinload(models.Question.answers),
        )
        .where(models.Quiz.visibility == visibility)
        .order_by(models.Quiz.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    quizzes = result.scalars().all()

    has_more = skip + len(quizzes) < total

    return PaginatedQuizResponse(
        quizzes=[QuizPublic.model_validate(quiz) for quiz in quizzes],
        skip=skip,
        limit=limit,
        total=total,
        has_more=has_more,
    )


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
    )

    db.add(new_quiz)
    await db.flush()

    for question in quiz.questions:
        new_question = models.Question(
            text=question.text,
            type=question.type,
            position=question.position,
            quiz_id=new_quiz.id,
        )
        db.add(new_question)
        await db.flush()
        for answer in question.answers:
            db.add(
                models.AnswerOption(
                    text=answer.text,
                    is_correct=answer.is_correct,
                    question_id=new_question.id,
                )
            )

    await db.commit()

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.questions).selectinload(models.Question.answers),
        )
        .where(models.Quiz.id == new_quiz.id)
    )

    quiz_ = result.scalars().first()
    return quiz_
