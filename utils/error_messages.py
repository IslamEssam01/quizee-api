class UserErrors:
    DUPLICATE_USERNAME = "A user with this username already exists"
    DUPLICATE_EMAIL = "A user with this email already exists"
    USER_NOT_FOUND = "User not found"
    NOT_AUTHORIZED_TO_UPDATE_USER = "Not authorized to update this user"
    NOT_AUTHORIZED_TO_DELETE_USER = "Not authorized to delete this user"
    INCORRECT_CURRENT_PASSWORD = "Incorrect password"


class AuthErrors:
    INCORRECT_EMAIL_OR_PASSWORD = "Incorrect email or password"
    INVALID_TOKEN = "Invalid or expired token"
    USER_NOT_FOUND = "User not found"
    REFRESH_TOKEN_MISSING = "Refresh token is missing"
    RATE_LIMIT_REACHED = "Too many attempts. Please try again later"


class QuizErrors:
    NO_CORRECT_ANSWER = "A question has no correct answer provided"
    DUPLICATE_QUESTION = "A question with duplicate id exists"
    DUPLICATE_ANSWER = "An answer with duplicate id exists"
    QUIZ_NOT_FOUND = "Quiz not found"
    NOT_AUTHORIZED_TO_VIEW_QUIZ = "Not authorized to view this quiz"
    NOT_AUTHORIZED_TO_UPDATE_QUIZ = "Not authorized to update this quiz"
    NOT_AUTHORIZED_TO_DELETE_QUIZ = "Not authorized to delete this quiz"
    ATTEMPT_MUST_HAVE_USER_OR_NAME = "An attempt must have a user or a taker name"
    ATTEMPT_NOT_FOUND = "Attempt not found"
    NOT_AUTHORIZED_TO_SUBMIT_ATTEMPT = "Not authorized to submit this attempt"
    INVALID_ANSWER_FIELDS = "Only one of 'answer_id' or 'answer_ids' should be provided"
    MISSING_ANSWER_FIELDS = (
        "At least one of 'answer_id' or 'answer_ids' must be provided"
    )
    INVALID_QUESTION_POINTS = "Answer points must sum up to the question's points value"
    NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ = "Not authorized to take this private quiz"
    NOT_AUTHORIZED_TO_DUPLICATE_QUIZ = "Not authorized to duplicate this quiz"
    NOT_AUTHORIZED_TO_RESUME_ATTEMPT = "Not authorized to resume this attempt"
    NOT_AUTHORIZED_TO_UPDATE_ATTEMPT = "Not authorized to update this attempt"
    ATTEMPT_ALREADY_SUBMITTED = (
        "This attempt has already been submitted and cannot be updated"
    )
    INVALID_GRADE_TIERS = "Grade tiers thresholds must be between 0 and 100"
    INVALID_GRADE_TIER_NAME = "Grade tier names must be 20 characters or less"
