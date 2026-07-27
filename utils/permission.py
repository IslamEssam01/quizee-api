from enum import StrEnum

import models


class Action(StrEnum):
    VIEW = "view"
    EDIT = "edit"
    DELETE = "delete"


def can_user_do(user: models.User, action: Action, owner_id: int):
    # Just check ownership for now

    return user.id == owner_id
