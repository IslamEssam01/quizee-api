from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

import models
from database import DBSession
from schemas.quiz import (
    AttemptResponse,
    AttemptSummary,
    PaginatedQuizPublicResponse,
    PrivateQuizAttempt,
    PublicQuizAttempt,
    QuestionPrivate,
    QuizCreate,
    QuizPrivate,
    QuizPublic,
    QuizUpdate,
    StartAttemptRequest,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    UpdateAccessRequest,
    UpdateAccessResponse,
    UpdateAttemptResponse,
)
from utils.auth import CurrentUser, OptionalAccessToken, get_current_user
from utils.enums import Visibility
from utils.error_messages import QuizErrors
from utils.permission import Action, can_user_do_for_quiz
from utils.quizzes import (
    calculate_pass_rate,
    calculate_score,
    get_attempts_count,
    get_quiz_attempts,
    get_quizzes_with_options,
    is_attempt_passed,
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


@router.post("/{quiz_id}/start-attempt", response_model=AttemptResponse)
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

    sort_quiz_questions(quiz.questions)

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

    attempt = models.Attempt(
        quiz_id=quiz.id,
        user_id=user.id if user else None,
        quiz_json=PrivateQuizAttempt.model_validate(quiz).model_dump(mode="json"),
        taker_name=request_data.taker_name if request_data else None,
    )

    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return AttemptResponse(id=attempt.id, quiz=PublicQuizAttempt.model_validate(quiz))


@router.post("/resume-attempt/{attempt_id}", response_model=AttemptResponse)
async def resume_attempt(
    attempt_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    result = await db.execute(
        select(models.Attempt).where(models.Attempt.id == attempt_id)
    )
    attempt = result.scalars().first()
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.ATTEMPT_NOT_FOUND
        )

    if not attempt.user_id or attempt.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_RESUME_ATTEMPT,
        )

    quiz_json = attempt.quiz_json

    return AttemptResponse(
        id=attempt.id, quiz=PublicQuizAttempt.model_validate(quiz_json)
    )


@router.patch("/update-attempt/{attempt_id}", response_model=UpdateAttemptResponse)
async def update_attempt(
    attempt_id: int,
    db: DBSession,
    request_data: SubmitAttemptRequest | None = None,
    token: OptionalAccessToken = None,
):
    result = await db.execute(
        select(models.Attempt).where(models.Attempt.id == attempt_id)
    )
    attempt = result.scalars().first()

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.ATTEMPT_NOT_FOUND
        )

    if attempt.taken_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=QuizErrors.ATTEMPT_ALREADY_SUBMITTED,
        )

    user = None
    if token:
        try:
            user = await get_current_user(token, db)
        except:
            pass

    if attempt.user_id and (not user or not user.id == attempt.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_UPDATE_ATTEMPT,
        )

    if not attempt.quiz_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    if request_data:
        attempt.answers_json = (
            [answer.model_dump(mode="json") for answer in request_data.answers]
            if request_data
            else None
        )

    await db.commit()
    await db.refresh(attempt)

    return attempt


@router.post("/submit-attempt/{attempt_id}", response_model=SubmitAttemptResponse)
async def submit_attempt(
    attempt_id: int,
    db: DBSession,
    request_data: SubmitAttemptRequest | None = None,
    token: OptionalAccessToken = None,
):
    result = await db.execute(
        select(models.Attempt).where(models.Attempt.id == attempt_id)
    )
    attempt = result.scalars().first()

    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.ATTEMPT_NOT_FOUND
        )

    user = None
    if token:
        try:
            user = await get_current_user(token, db)
        except:
            pass

    if attempt.user_id and (not user or not user.id == attempt.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=QuizErrors.NOT_AUTHORIZED_TO_SUBMIT_ATTEMPT,
        )

    if not attempt.quiz_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=QuizErrors.QUIZ_NOT_FOUND
        )

    score = 0
    passed = False

    if request_data:
        score = calculate_score(
            questions=[
                QuestionPrivate.model_validate(question)
                for question in attempt.quiz_json["questions"]
            ],
            answers=request_data.answers,
            allow_negative_score=attempt.quiz_json.get("allow_negative_score", True),
        )

        passed = is_attempt_passed(
            PrivateQuizAttempt.model_validate(attempt.quiz_json), score
        )

    attempt.score = score
    attempt.passed = passed
    attempt.taken_at = datetime.now(UTC)
    attempt.answers_json = (
        [answer.model_dump(mode="json") for answer in request_data.answers]
        if request_data
        else None
    )
    if attempt.quiz_json.get("grade_tiers", None):
        total_points = sum(
            question["points"] for question in attempt.quiz_json["questions"]
        )
        for grade, threshold in sorted(
            attempt.quiz_json["grade_tiers"].items(), key=lambda x: x[1], reverse=True
        ):
            if (score / total_points) * 100 >= threshold:
                attempt.grade = grade
                break

    await db.commit()
    await db.refresh(attempt)

    return attempt


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
