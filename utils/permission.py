from enum import StrEnum

import models


class Action(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"


def can_user_do_for_quiz(user: models.User, action: Action, quiz: models.Quiz):
    # Just check ownership for now

    return user.id == quiz.owner_id
