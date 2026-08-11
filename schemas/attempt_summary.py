from datetime import datetime

from schemas.base import BaseResponse


class AttemptSummary(BaseResponse):
    id: int
    user_id: int | None
    taker_name: str | None
    started_at: datetime
    taken_at: datetime | None
    score: float | None
    passed: bool | None
