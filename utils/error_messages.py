class UserErrors:
    DUPLICATE_USERNAME = "A user with this username already exists"
    DUPLICATE_EMAIL = "A user with this email already exists"
    USER_NOT_FOUND = "User not found"


class AuthErrors:
    INCORRECT_EMAIL_OR_PASSWORD = "Incorrect email or password"
    INVALID_TOKEN = "Invalid or expired token"
    USER_NOT_FOUND = "User not found"
