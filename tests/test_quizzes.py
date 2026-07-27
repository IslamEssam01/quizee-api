from typing import Any, TypedDict

import pytest
from httpx import AsyncClient

import models
from models.question import QuestionType
from tests.conftest import auth_header, create_test_user, login_user
from utils.error_messages import QuizErrors


class TestAnswer(TypedDict):
    text: str
    is_correct: bool


class TestQuestion(TypedDict):
    text: str
    position: int
    type: str
    answers: list[TestAnswer]


class TestQuiz(TypedDict):
    title: str
    description: str
    owner_id: int
    visibility: str
    pass_threshold: int
    questions: list[TestQuestion]


async def create_test_quiz(user: Any):
    quiz: TestQuiz = {
        "title": "test quiz",
        "description": "testing create quiz",
        "owner_id": user["id"],
        "visibility": "public",
        "pass_threshold": 50,
        "questions": [
            {
                "text": "question 1",
                "position": 1,
                "type": QuestionType.MCQ,
                "answers": [
                    {"text": "answer 1", "is_correct": True},
                    {"text": "answer 2", "is_correct": False},
                    {"text": "answer 3", "is_correct": False},
                ],
            },
            {
                "text": "question 2",
                "position": 2,
                "type": QuestionType.MCQ,
                "answers": [
                    {"text": "answer 1", "is_correct": False},
                    {"text": "answer 2", "is_correct": True},
                    {"text": "answer 3", "is_correct": False},
                ],
            },
            {
                "text": "question 3",
                "position": 3,
                "type": QuestionType.TRUE_OR_FALSE,
                "answers": [
                    {"text": "true", "is_correct": True},
                    {"text": "false", "is_correct": False},
                ],
            },
        ],
    }

    return quiz


def check_quiz_matches(data, user, quiz: TestQuiz, is_public: bool = True):
    assert data.keys() == {
        "id",
        "title",
        "owner_id",
        "owner",
        "description",
        "visibility",
        "questions",
        "pass_threshold",
    }

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

    check_quiz_matches(data["quizzes"][0], user, quiz1, True)
    check_quiz_matches(data["quizzes"][1], user, quiz2, True)


@pytest.mark.anyio
async def test_get_user_quizzes(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user2")
    token, _ = await login_user(client)

    quiz1 = await create_test_quiz(user)
    quiz2 = await create_test_quiz(user)
    await create_test_quiz(user2)
    await create_test_quiz(user2)

    await client.post("/api/quizzes", json=quiz1, headers=auth_header(token))
    await client.post("/api/quizzes", json=quiz2, headers=auth_header(token))

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
