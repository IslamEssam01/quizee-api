import random
from copy import deepcopy
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from routers import attempts
from schemas.attempt import (
    AttemptQuizPrivate,
    AttemptQuizPublic,
    AttemptResponse,
    StartAttemptRequest,
)
from schemas.attempt_summary import AttemptSummary
from schemas.quiz import (
    PaginatedQuizPublicResponse,
    QuizCreate,
    QuizPrivate,
    QuizPublic,
    QuizUpdate,
    UpdateAccessRequest,
    UpdateAccessResponse,
)
from utils.auth import CurrentUser, OptionalAccessToken, get_current_user
from utils.enums import Visibility
from utils.error_messages import QuizErrors
from utils.permission import Action, can_user_do_for_quiz
from utils.quizzes import (
    calculate_pass_rate,
    get_attempts_count,
    get_quiz_attempts,
    get_quizzes_with_options,
    sort_quiz_questions,
    validate_quiz_questions,
)

router = APIRouter()


@router.get("", response_model=PaginatedQuizPublicResponse)
async def get_quizzes(
    db: DBSession,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
):
    return await get_quizzes_with_options(
        db=db, skip=skip, limit=limit, visibility=Visibility.PUBLIC
    )


@router.get("/{quiz_id}", response_model=QuizPublic | QuizPrivate)
async def get_quiz(
    quiz_id: int,
    db: DBSession,
    token: OptionalAccessToken = None,
):
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
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

    can_view_private = bool(user) and (
        await can_user_do_for_quiz(user, Action.VIEW, quiz, db)
    )

    if quiz.visibility != Visibility.PUBLIC and not can_view_private:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_VIEW_QUIZ,
        )

    sort_quiz_questions(quiz.questions)

    if not can_view_private:
        attempts_count = await get_attempts_count(db, quiz.id)
        return QuizPublic.model_validate(quiz).model_copy(
            update={"attempts_count": attempts_count}
        )

    attempts = await get_quiz_attempts(db, quiz.id)
    return QuizPrivate.model_validate(quiz).model_copy(
        update={
            "attempts_count": len(attempts),
            "pass_rate": calculate_pass_rate(attempts),
            "attempts_summary": [AttemptSummary.model_validate(a) for a in attempts],
        }
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=QuizPrivate)
async def create_quiz(quiz: QuizCreate, current_user: CurrentUser, db: DBSession):
    validate_quiz_questions(quiz.questions)

    new_quiz = models.Quiz(
        title=quiz.title,
        description=quiz.description,
        visibility=quiz.visibility,
        pass_threshold=quiz.pass_threshold,
        owner_id=current_user.id,
        questions=[question.model_dump(mode="json") for question in quiz.questions],
        allow_negative_score=quiz.allow_negative_score,
        grade_tiers=quiz.grade_tiers,
        randomize_questions=quiz.randomize_questions,
        randomize_answers=quiz.randomize_answers,
    )

    db.add(new_quiz)

    await db.commit()
    await db.refresh(new_quiz)

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
        )
        .where(models.Quiz.id == new_quiz.id)
    )

    quiz_db = result.scalars().first()

    if not quiz_db:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    sort_quiz_questions(quiz_db.questions)

    return new_quiz


@router.patch("/{quiz_id}", response_model=QuizPrivate)
async def update_quiz(
    quiz_id: int, quiz_update: QuizUpdate, current_user: CurrentUser, db: DBSession
):
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
        )
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if not (await can_user_do_for_quiz(current_user, Action.EDIT, quiz, db)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_UPDATE_QUIZ,
        )

    if quiz_update.questions:
        validate_quiz_questions(quiz_update.questions)

    update_data = quiz_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(quiz, key, value)

    await db.commit()
    await db.refresh(quiz)

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

    if not (await can_user_do_for_quiz(current_user, Action.EDIT, quiz, db)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_DELETE_QUIZ,
        )

    await db.delete(quiz)
    await db.commit()


@router.post("/{quiz_id}/attempts", response_model=AttemptResponse)
async def start_attempt(
    quiz_id: int,
    db: DBSession,
    request_data: StartAttemptRequest | None = None,
    token: OptionalAccessToken = None,
):
    result = await db.execute(
        select(models.Quiz)
        .options(selectinload(models.Quiz.owner))
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

    if not user and (not request_data or not request_data.taker_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=QuizErrors.ATTEMPT_MUST_HAVE_USER_OR_NAME,
        )

    if not (await can_user_do_for_quiz(user, Action.VIEW, quiz, db)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ,
        )

    quiz = deepcopy(quiz)

    if quiz.randomize_questions:
        random.shuffle(quiz.questions)
    else:
        sort_quiz_questions(quiz.questions)

    if quiz.randomize_answers:
        for question in quiz.questions:
            if "answers" in question and isinstance(question["answers"], list):
                random.shuffle(question["answers"])

    attempt = models.Attempt(
        quiz_id=quiz.id,
        user_id=user.id if user else None,
        quiz_json=AttemptQuizPrivate.model_validate(quiz).model_dump(mode="json"),
        taker_name=request_data.taker_name if request_data else None,
    )

    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return AttemptResponse(id=attempt.id, quiz=AttemptQuizPublic.model_validate(quiz))


@router.patch("/{quiz_id}/update-access", response_model=UpdateAccessResponse)
async def update_quiz_access(
    quiz_id: int,
    request_data: UpdateAccessRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
        )
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if not (await can_user_do_for_quiz(current_user, Action.EDIT, quiz, db)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_UPDATE_QUIZ,
        )

    granted_user_ids: list[int] = []
    revoked_user_ids: list[int] = []

    for user_str in request_data.grant_users:
        result = await db.execute(
            select(models.User).where(
                (func.lower(models.User.username) == user_str.lower())
                | (func.lower(models.User.email) == user_str.lower())
            )
        )

        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_str}' not found.",
            )

        existing_access = next(
            (access for access in quiz.quiz_access if access.user_id == user.id), None
        )
        if not existing_access:
            new_access = models.QuizAccess(
                quiz_id=quiz.id, user_id=user.id, granted_by=current_user.id
            )
            db.add(new_access)
            granted_user_ids.append(user.id)

    for user_str in request_data.revoke_users:
        result = await db.execute(
            select(models.User).where(
                (func.lower(models.User.username) == user_str.lower())
                | (func.lower(models.User.email) == user_str.lower())
            )
        )
        user = result.scalars().first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User '{user_str}' not found.",
            )

        existing_access = next(
            (access for access in quiz.quiz_access if access.user_id == user.id), None
        )
        if existing_access:
            await db.delete(existing_access)
            revoked_user_ids.append(user.id)

    await db.commit()

    return UpdateAccessResponse(
        quiz_id=quiz.id,
        granted_user_ids=granted_user_ids,
        revoked_user_ids=revoked_user_ids,
    )


@router.post(
    "/{quiz_id}/duplicate",
    response_model=QuizPrivate,
    status_code=status.HTTP_201_CREATED,
)
async def duplicate_quiz(
    quiz_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
        )
        .where(models.Quiz.id == quiz_id)
    )
    quiz = result.scalars().first()
    if not quiz:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if not (await can_user_do_for_quiz(current_user, Action.DUPLICATE, quiz, db)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_DUPLICATE_QUIZ,
        )

    new_quiz = models.Quiz(
        title=f"Copy of {quiz.title}",
        description=quiz.description,
        visibility=quiz.visibility,
        pass_threshold=quiz.pass_threshold,
        owner_id=current_user.id,
        questions=quiz.questions,
        allow_negative_score=quiz.allow_negative_score,
        grade_tiers=quiz.grade_tiers,
        randomize_questions=quiz.randomize_questions,
        randomize_answers=quiz.randomize_answers,
    )

    db.add(new_quiz)
    await db.commit()
    await db.refresh(new_quiz)

    sort_quiz_questions(new_quiz.questions)

    result = await db.execute(
        select(models.Quiz)
        .options(
            selectinload(models.Quiz.owner),
            selectinload(models.Quiz.quiz_access).selectinload(models.QuizAccess.user),
        )
        .where(models.Quiz.id == new_quiz.id)
    )

    quiz_db = result.scalars().first()

    return quiz_db


router.include_router(attempts.router, prefix="/attempts", tags=["Attempts"])
