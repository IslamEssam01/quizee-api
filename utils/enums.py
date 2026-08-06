import enum


class Visibility(enum.StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    PUBLIC_WITH_LINK = "public_with_link"


class QuestionType(enum.StrEnum):
    MCQ = "mcq"
    TRUE_OR_FALSE = "T OR F"


class GradingMode(enum.StrEnum):
    ALL_OR_NOTHING = "all_or_nothing"
    PARTIAL_CREDIT = "partial_credit"
