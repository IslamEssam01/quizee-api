from enum import StrEnum

import models
from database import DBSession
from utils.enums import Visibility


class Action(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"


async def can_user_do_for_quiz(
    user: models.User | None, action: Action, quiz: models.Quiz, db: DBSession
):
    if user and user.id == quiz.owner_id:
        return True

    if action is Action.VIEW:
        if quiz.visibility == Visibility.PUBLIC:
            return True
        elif quiz.visibility == Visibility.PRIVATE:
            if user is None:
                return False
            result = await db.execute(
                models.QuizAccess.__table__.select().where(
                    (models.QuizAccess.quiz_id == quiz.id),
                    (models.QuizAccess.user_id == user.id),
                )
            )
            access = result.scalars().first()
            return access is not None

    return False
