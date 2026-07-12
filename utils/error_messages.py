class UserErrors:
    DUPLICATE_USERNAME = "A user with this username already exists"
    DUPLICATE_EMAIL = "A user with this email already exists"
    USER_NOT_FOUND = "User not found"
    NOT_AUTHORIZED_TO_UPDATE_USER = "Not authorized to update this user"
    NOT_AUTHORIZED_TO_DELETE_USER = "Not authorized to delete this user"


class AuthErrors:
    INCORRECT_EMAIL_OR_PASSWORD = "Incorrect email or password"
    INVALID_TOKEN = "Invalid or expired token"
    USER_NOT_FOUND = "User not found"
    REFRESH_TOKEN_MISSING = "Refresh token is missing"
