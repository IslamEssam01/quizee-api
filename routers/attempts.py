from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

import models
from database import DBSession
from schemas.attempt import (
    AttemptQuizPrivate,
    AttemptQuizPublic,
    AttemptResponse,
    SubmitAttemptRequest,
    SubmitAttemptResponse,
    UpdateAttemptResponse,
)
from schemas.question import QuestionPrivate
from utils.auth import CurrentUser, OptionalAccessToken, get_current_user
from utils.error_messages import QuizErrors
from utils.quizzes import calculate_score, is_attempt_passed

router = APIRouter()


@router.post("/resume/{attempt_id}", response_model=AttemptResponse)
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
        id=attempt.id, quiz=AttemptQuizPublic.model_validate(quiz_json)
    )


@router.patch("/{attempt_id}", response_model=UpdateAttemptResponse)
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


@router.post("/submit/{attempt_id}", response_model=SubmitAttemptResponse)
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
            AttemptQuizPrivate.model_validate(attempt.quiz_json), score
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

        if attempt.grade is None:
            # if all loops fail, assign the lowest grade because of negative scores
            attempt.grade = min(
                attempt.quiz_json["grade_tiers"],
                key=attempt.quiz_json["grade_tiers"].get,
            )

    await db.commit()
    await db.refresh(attempt)

    return attempt
