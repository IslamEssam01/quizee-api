import enum


class Visibility(enum.StrEnum):
    PUBLIC = "public"


class QuestionType(enum.StrEnum):
    MCQ = "mcq"
    TRUE_OR_FALSE = "T OR F"
