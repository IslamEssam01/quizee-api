from typing import TypedDict

import pytest
from httpx import AsyncClient

from models.question import QuestionType
from tests.conftest import auth_header, create_test_user, login_user


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


@pytest.mark.anyio
async def test_create_quiz(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
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
                "type": QuestionType.MCQ.value,
                "answers": [
                    {"text": "answer 1", "is_correct": True},
                    {"text": "answer 2", "is_correct": False},
                    {"text": "answer 3", "is_correct": False},
                ],
            },
            {
                "text": "question 2",
                "position": 2,
                "type": QuestionType.MCQ.value,
                "answers": [
                    {"text": "answer 1", "is_correct": False},
                    {"text": "answer 2", "is_correct": True},
                    {"text": "answer 3", "is_correct": False},
                ],
            },
            {
                "text": "question 3",
                "position": 3,
                "type": QuestionType.TRUE_OR_FALSE.value,
                "answers": [
                    {"text": "true", "is_correct": True},
                    {"text": "false", "is_correct": False},
                ],
            },
        ],
    }

    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    assert response.status_code == 201

    data = response.json()
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
            assert (
                response_question["answers"][j]["is_correct"]
                == quiz_question["answers"][j]["is_correct"]
            )

    assert data["owner_id"] == user["id"]
