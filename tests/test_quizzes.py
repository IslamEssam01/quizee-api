import copy
from typing import Any, NotRequired, TypedDict

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user
from utils.enums import GradingMode, QuestionType
from utils.error_messages import QuizErrors
from utils.quizzes import sort_quiz_questions


class TestAnswer(TypedDict):
    id: int
    text: str
    is_correct: bool
    points: NotRequired[int]


class TestQuestion(TypedDict):
    id: int
    text: str
    position: int
    type: str
    answers: list[TestAnswer]
    points: NotRequired[float]
    grading_mode: NotRequired[GradingMode]
    penalty_per_wrong: NotRequired[float]


class TestQuiz(TypedDict):
    title: str
    description: str
    owner_id: int
    visibility: str
    pass_threshold: int
    questions: list[TestQuestion]
    allow_negative_score: NotRequired[bool]
    grade_tiers: NotRequired[dict[str, int]]


async def create_test_quiz(user: Any):
    quiz: TestQuiz = {
        "title": "test quiz",
        "description": "testing create quiz",
        "owner_id": user["id"],
        "visibility": "public",
        "pass_threshold": 50,
        "questions": [
            {
                "id": 1,
                "text": "question 1",
                "position": 1,
                "type": QuestionType.MCQ,
                "answers": [
                    {"id": 1, "text": "answer 1", "is_correct": True},
                    {"id": 2, "text": "answer 2", "is_correct": False},
                    {"id": 3, "text": "answer 3", "is_correct": False},
                ],
            },
            {
                "id": 2,
                "text": "question 2",
                "position": 2,
                "type": QuestionType.MCQ,
                "answers": [
                    {"id": 1, "text": "answer 1", "is_correct": False},
                    {"id": 2, "text": "answer 2", "is_correct": True},
                    {"id": 3, "text": "answer 3", "is_correct": False},
                ],
            },
            {
                "id": 3,
                "text": "question 3",
                "position": 3,
                "type": QuestionType.TRUE_OR_FALSE,
                "answers": [
                    {"id": 1, "text": "true", "is_correct": True},
                    {"id": 2, "text": "false", "is_correct": False},
                ],
            },
        ],
    }

    return quiz


def check_quiz_matches(
    data, user, quiz: TestQuiz, is_public: bool = True, exclude_keys: set[str] = set()
):
    base_keys = {
        "id",
        "title",
        "owner_id",
        "owner",
        "description",
        "visibility",
        "questions",
        "pass_threshold",
        "attempts_count",
        "allow_negative_score",
        "grade_tiers",
        "randomize_questions",
        "randomize_answers",
    }

    for key in exclude_keys:
        base_keys.remove(key)

    if is_public:
        assert data.keys() == base_keys
    else:
        assert data.keys() == base_keys | {
            "pass_rate",
            "attempts_summary",
            "quiz_access",
        }
        assert data["pass_rate"] == 0.0
        assert data["attempts_summary"] == []

    if "attempts_count" in base_keys:
        assert data["attempts_count"] == 0

    assert isinstance(data["questions"], list)
    assert data["title"] == quiz["title"]
    assert data["owner_id"] == quiz["owner_id"]
    assert data["description"] == quiz["description"]
    assert data["visibility"] == quiz["visibility"]
    assert data["pass_threshold"] == quiz["pass_threshold"]
    assert len(data["questions"]) == len(quiz["questions"])
    for i in range(len(quiz["questions"])):
        response_question = data["questions"][i]
        quiz_question = quiz["questions"][i]
        assert response_question["text"] == quiz_question["text"]
        assert response_question["position"] == quiz_question["position"]
        assert response_question["type"] == quiz_question["type"]
        assert len(response_question["answers"]) == len(quiz_question["answers"])
        for j in range(len(quiz_question["answers"])):
            assert (
                response_question["answers"][j]["text"]
                == quiz_question["answers"][j]["text"]
            )
            if not is_public:
                assert (
                    response_question["answers"][j]["is_correct"]
                    == quiz_question["answers"][j]["is_correct"]
                )

    assert data["owner_id"] == user["id"]


@pytest.mark.anyio
async def test_create_quiz(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)

    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    assert response.status_code == 201

    data = response.json()
    check_quiz_matches(data, user, quiz, False)


@pytest.mark.anyio
async def test_create_quiz_duplicate_question_id(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)
    quiz["questions"][1]["id"] = quiz["questions"][0]["id"]

    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.DUPLICATE_QUESTION


@pytest.mark.anyio
async def test_create_quiz_duplicate_answer_id(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)
    quiz["questions"][0]["answers"][1]["id"] = quiz["questions"][0]["answers"][0]["id"]

    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.DUPLICATE_ANSWER


@pytest.mark.anyio
async def test_get_quizzes(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)

    await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    response = await client.get("/api/quizzes")

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"quizzes", "skip", "limit", "total", "has_more"}
    assert isinstance(data["quizzes"], list)
    assert data["skip"] == 0
    assert data["total"] == 1
    assert data["has_more"] == False
    assert len(data["quizzes"]) == 1

    data = data["quizzes"][0]
    check_quiz_matches(data, user, quiz, True)


@pytest.mark.anyio
async def test_get_current_user_quizzes(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user2")
    token, _ = await login_user(client)
    token2, _ = await login_user(client, email="user2@test.com")

    quiz1 = await create_test_quiz(user)
    quiz2 = await create_test_quiz(user)
    quiz3 = await create_test_quiz(user2)
    quiz4 = await create_test_quiz(user2)

    await client.post("/api/quizzes", json=quiz1, headers=auth_header(token))
    await client.post("/api/quizzes", json=quiz2, headers=auth_header(token))

    await client.post("/api/quizzes", json=quiz3, headers=auth_header(token2))
    await client.post("/api/quizzes", json=quiz4, headers=auth_header(token2))

    response = await client.get("/api/users/me/quizzes", headers=auth_header(token))

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"quizzes", "skip", "limit", "total", "has_more"}
    assert isinstance(data["quizzes"], list)
    assert data["skip"] == 0
    assert data["total"] == 2
    assert data["has_more"] == False
    assert len(data["quizzes"]) == 2

    check_quiz_matches(data["quizzes"][0], user, quiz1, False)
    check_quiz_matches(data["quizzes"][1], user, quiz2, False)


@pytest.mark.anyio
async def test_get_user_quizzes(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user2")
    token, _ = await login_user(client)
    token2, _ = await login_user(client, email="user2@test.com")

    quiz1 = await create_test_quiz(user)
    quiz2 = await create_test_quiz(user)
    quiz3 = await create_test_quiz(user2)
    quiz4 = await create_test_quiz(user2)

    await client.post("/api/quizzes", json=quiz1, headers=auth_header(token))
    await client.post("/api/quizzes", json=quiz2, headers=auth_header(token))
    await client.post("/api/quizzes", json=quiz3, headers=auth_header(token2))
    await client.post("/api/quizzes", json=quiz4, headers=auth_header(token2))

    response = await client.get(
        f"/api/users/{user["id"]}/quizzes",
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"quizzes", "skip", "limit", "total", "has_more"}
    assert isinstance(data["quizzes"], list)
    assert data["skip"] == 0
    assert data["total"] == 2
    assert data["has_more"] == False
    assert len(data["quizzes"]) == 2

    check_quiz_matches(data["quizzes"][0], user, quiz1, True)
    check_quiz_matches(data["quizzes"][1], user, quiz2, True)


@pytest.mark.anyio
async def test_get_not_found_quiz_by_id(client: AsyncClient):
    response = await client.get("/api/quizzes/999")

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_get_quiz_by_id(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)

    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    response = await client.get(f"/api/quizzes/{data["id"]}")

    assert response.status_code == 200
    data = response.json()
    check_quiz_matches(data, user, quiz, True)


@pytest.mark.anyio
async def test_update_quiz_not_found(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.patch(
        "/api/quizzes/999",
        json={"title": "new_title"},
        headers=auth_header(token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_update_quiz_unathorized(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user2")
    token2, _ = await login_user(client, email="user2@test.com")

    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    response = await client.patch(
        f"/api/quizzes/{data['id']}",
        json={"title": "new_title"},
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_UPDATE_QUIZ


@pytest.mark.anyio
async def test_update_quiz_successfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    questions: list[TestQuestion] = quiz["questions"][:-1]
    questions[1]["position"] = 3
    questions.append(
        {
            "id": 4,
            "text": "test question",
            "position": 1,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
            ],
            "type": "mcq",
        }
    )

    new_quiz = copy.deepcopy(quiz)
    new_quiz["questions"] = questions
    new_quiz["title"] = "new_title"

    response = await client.patch(
        f"/api/quizzes/{data['id']}",
        json={"questions": questions, "title": "new_title"},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    sort_quiz_questions(new_quiz["questions"])

    check_quiz_matches(data, user, new_quiz, False)


@pytest.mark.anyio
async def test_update_quiz_duplicate_question_id(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    questions: list[TestQuestion] = copy.deepcopy(quiz["questions"])
    questions[1]["id"] = questions[0]["id"]

    response = await client.patch(
        f"/api/quizzes/{data['id']}",
        json={"questions": questions},
        headers=auth_header(token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.DUPLICATE_QUESTION


@pytest.mark.anyio
async def test_update_quiz_duplicate_answer_id(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    questions: list[TestQuestion] = copy.deepcopy(quiz["questions"])
    questions[0]["answers"][1]["id"] = questions[0]["answers"][0]["id"]

    response = await client.patch(
        f"/api/quizzes/{data['id']}",
        json={"questions": questions},
        headers=auth_header(token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.DUPLICATE_ANSWER


@pytest.mark.anyio
async def test_delete_quiz_not_found(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.delete(
        "/api/quizzes/999",
        headers=auth_header(token),
    )

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_delete_quiz_unathorized(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user2")
    token2, _ = await login_user(client, email="user2@test.com")

    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    response = await client.delete(
        f"/api/quizzes/{data['id']}",
        headers=auth_header(token2),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_DELETE_QUIZ


@pytest.mark.anyio
async def test_delete_quiz_successfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()

    response = await client.delete(
        f"/api/quizzes/{data['id']}",
        headers=auth_header(token),
    )

    assert response.status_code == 204

    response = await client.get(
        f"/api/quizzes/{data["id"]}",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_duplicate_quiz_unathorized(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@example.com", username="user2")
    token2, _ = await login_user(client, email=user2["email"])

    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    quiz_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/duplicate",
        headers=auth_header(token2),
    )
    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_DUPLICATE_QUIZ


@pytest.mark.anyio
async def test_duplicate_quiz_successfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)

    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    quiz_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/duplicate",
        headers=auth_header(token),
    )
    assert response.status_code == 201
    data = response.json()
    new_quiz = copy.deepcopy(quiz)
    new_quiz["title"] = f"Copy of {quiz['title']}"
    check_quiz_matches(data, user, new_quiz, False)
