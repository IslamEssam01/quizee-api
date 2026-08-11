import copy
from typing import Any, NotRequired, TypedDict

import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user
from utils.enums import GradingMode, QuestionType, Visibility
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
async def test_start_attempt_for_unknown_quiz(client: AsyncClient):
    response = await client.post(
        "/api/quizzes/999/start-attempt",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_start_attempt_fail(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt",
    )

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.ATTEMPT_MUST_HAVE_USER_OR_NAME


@pytest.mark.anyio
async def test_start_attempt_with_user(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user 2")
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt",
        headers=auth_header(token2),
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}

    check_quiz_matches(
        data["quiz"], user, quiz, True, exclude_keys={"attempts_count", "owner"}
    )


@pytest.mark.anyio
async def test_start_attempt_with_taker_name(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", json={"taker_name": "taker"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}
    check_quiz_matches(
        data["quiz"], user, quiz, True, exclude_keys={"attempts_count", "owner"}
    )


@pytest.mark.anyio
async def test_submit_unknown_attempt(client: AsyncClient):
    response = await client.post("/api/quizzes/submit-attempt/999")
    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.ATTEMPT_NOT_FOUND


@pytest.mark.anyio
async def test_submit_another_user_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@example.com", username="user2")
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )
    data = response.json()
    attempt_id = data["id"]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}", headers=auth_header(token)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_SUBMIT_ATTEMPT


@pytest.mark.anyio
async def test_submit_deleted_quiz_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    await client.delete(f"/api/quizzes/{quiz_id}", headers=auth_header(token))

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}", headers=auth_header(token)
    )

    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.QUIZ_NOT_FOUND


@pytest.mark.anyio
async def test_submit_attempt_succesfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    get_correct_answer = lambda question: [
        answer for answer in question["answers"] if answer["is_correct"]
    ][0]

    get_wrong_answer = lambda question: [
        answer for answer in question["answers"] if not answer["is_correct"]
    ][0]

    answers = []
    score = 0
    for question in quiz["questions"][: len(quiz["questions"]) // 2 + 1]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_correct_answer(question)["id"],
            }
        )
        score += 1

    for question in quiz["questions"][len(quiz["questions"]) // 2 + 1 :]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_wrong_answer(question)["id"],
            }
        )

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {
        "id",
        "quiz_id",
        "user_id",
        "taker_name",
        "quiz_json",
        "answers_json",
        "started_at",
        "taken_at",
        "score",
        "passed",
        "grade",
    }

    assert data["id"] == attempt_id
    assert data["quiz_id"] == quiz_id
    assert data["user_id"] == user["id"]
    assert data["taker_name"] == None
    # check_quiz_matches(data["quiz_json"], user, quiz, False)
    for i in range(len(answers)):
        assert answers[i]["question_id"] == data["answers_json"][i]["question_id"]
        assert answers[i]["answer_id"] == data["answers_json"][i]["answer_id"]
    assert data["score"] == score
    assert data["passed"] == True


@pytest.mark.anyio
async def test_quiz_questions_with_points(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": False},
            ],
            "points": 2,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True},
                {"id": 3, "text": "answer 3", "is_correct": False},
            ],
            "points": 3,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_id": questions[0]["answers"][0]["id"],
        },
        {
            "question_id": questions[1]["id"],
            "answer_id": questions[1]["answers"][1]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 5

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_id": questions[0]["answers"][0]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 2

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[1]["id"],
            "answer_id": questions[1]["answers"][1]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 3


@pytest.mark.anyio
async def test_quiz_questions_with_multiple_answers(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_id": questions[1]["answers"][1]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][1]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][1]["id"],
                questions[1]["answers"][2]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][1]["id"],
                questions[1]["answers"][2]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 2


@pytest.mark.anyio
async def test_quiz_questions_with_partial_credit(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_id": questions[1]["answers"][1]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1.5

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][1]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][1]["id"],
                questions[1]["answers"][2]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][1]["id"],
                questions[1]["answers"][2]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 2


@pytest.mark.anyio
async def test_quiz_questions_answers_with_wrong_points(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "points": 2,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True, "points": 2},
                {"id": 3, "text": "answer 3", "is_correct": True, "points": 2},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "points": 3,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))

    assert response.status_code == 422


@pytest.mark.anyio
async def test_quiz_questions_answers_with_points(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "points": 2,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True, "points": 2},
                {"id": 3, "text": "answer 3", "is_correct": True, "points": 1},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "points": 3,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_id": questions[1]["answers"][1]["id"],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 4


@pytest.mark.anyio
async def test_quiz_questions_with_penalty(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "points": 2,
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "penalty_per_wrong": 1,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True, "points": 2},
                {"id": 3, "text": "answer 3", "is_correct": True, "points": 1},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "points": 3,
            "penalty_per_wrong": 0.5,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][0]["id"],
                questions[0]["answers"][1]["id"],
                questions[0]["answers"][2]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][0]["id"],
                questions[1]["answers"][1]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == -1.5


@pytest.mark.anyio
async def test_quiz_questions_with_negative_score(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "points": 2,
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "penalty_per_wrong": 1,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True, "points": 2},
                {"id": 3, "text": "answer 3", "is_correct": True, "points": 1},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "points": 3,
            "penalty_per_wrong": 0.5,
        },
    ]
    quiz["questions"] = questions
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][1]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][0]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == -1.5


@pytest.mark.anyio
async def test_quiz_questions_with_no_negative_score(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["questions"] = []
    questions: list[TestQuestion] = [
        {
            "text": "question 1",
            "id": 1,
            "position": 1,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": True},
                {"id": 2, "text": "answer 2", "is_correct": False},
                {"id": 3, "text": "answer 3", "is_correct": True},
            ],
            "points": 2,
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "penalty_per_wrong": 1,
        },
        {
            "text": "question 2",
            "id": 2,
            "position": 2,
            "type": QuestionType.MCQ,
            "answers": [
                {"id": 1, "text": "answer 1", "is_correct": False},
                {"id": 2, "text": "answer 2", "is_correct": True, "points": 2},
                {"id": 3, "text": "answer 3", "is_correct": True, "points": 1},
            ],
            "grading_mode": GradingMode.PARTIAL_CREDIT,
            "points": 3,
            "penalty_per_wrong": 0.5,
        },
    ]
    quiz["questions"] = questions
    quiz["allow_negative_score"] = False
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    answers = [
        {
            "question_id": questions[0]["id"],
            "answer_ids": [
                questions[0]["answers"][1]["id"],
            ],
        },
        {
            "question_id": questions[1]["id"],
            "answer_ids": [
                questions[1]["answers"][0]["id"],
            ],
        },
    ]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 0


@pytest.mark.anyio
async def test_taking_private_quiz_unathorized(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@example.com", username="user2")
    token, _ = await login_user(client)
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    quiz["visibility"] = Visibility.PRIVATE
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", json={"taker_name": "taker"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ


@pytest.mark.anyio
async def test_taking_private_quiz_successfully(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@example.com", username="user2")
    token, _ = await login_user(client)
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    quiz["visibility"] = Visibility.PRIVATE
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.patch(
        f"/api/quizzes/{quiz_id}/update-access",
        json={"grant_users": [user2["email"]]},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {
        "quiz_id",
        "granted_user_ids",
        "revoked_user_ids",
    }
    assert data["quiz_id"] == quiz_id
    assert data["granted_user_ids"] == [user2["id"]]
    assert data["revoked_user_ids"] == []

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    assert response.status_code == 200


@pytest.mark.anyio
async def test_revoking_private_quiz_access(client: AsyncClient):
    user = await create_test_user(client)
    user2 = await create_test_user(client, email="user2@example.com", username="user2")
    token, _ = await login_user(client)
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    quiz["visibility"] = Visibility.PRIVATE
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.patch(
        f"/api/quizzes/{quiz_id}/update-access",
        json={"grant_users": [user2["email"]]},
        headers=auth_header(token),
    )

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    assert response.status_code == 200

    response = await client.patch(
        f"/api/quizzes/{quiz_id}/update-access",
        json={"revoke_users": [user2["email"]]},
        headers=auth_header(token),
    )

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ


@pytest.mark.anyio
async def test_resume_unknown_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.post(
        "/api/quizzes/resume-attempt/999", headers=auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.ATTEMPT_NOT_FOUND


@pytest.mark.anyio
async def test_resume_another_user_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@exampl.com", username="user2")
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/resume-attempt/{attempt_id}", headers=auth_header(token)
    )
    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_RESUME_ATTEMPT


@pytest.mark.anyio
async def test_resume_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@test.com", username="user 2")
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt",
        headers=auth_header(token2),
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/resume-attempt/{attempt_id}",
        headers=auth_header(token2),
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}

    check_quiz_matches(
        data["quiz"], user, quiz, True, exclude_keys={"attempts_count", "owner"}
    )


@pytest.mark.anyio
async def test_update_unknown_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.patch(
        "/api/quizzes/update-attempt/999", headers=auth_header(token)
    )
    assert response.status_code == 404
    assert response.json()["detail"] == QuizErrors.ATTEMPT_NOT_FOUND


@pytest.mark.anyio
async def test_update_another_user_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    user2 = await create_test_user(client, email="user2@exampl.com", username="user2")
    token2, _ = await login_user(client, email=user2["email"])
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token2)
    )

    attempt_id = response.json()["id"]

    response = await client.patch(
        f"/api/quizzes/update-attempt/{attempt_id}", headers=auth_header(token)
    )
    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_UPDATE_ATTEMPT


@pytest.mark.anyio
async def test_update_attempt_succesfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    get_correct_answer = lambda question: [
        answer for answer in question["answers"] if answer["is_correct"]
    ][0]

    answers = []
    score = 0
    for question in quiz["questions"][: len(quiz["questions"]) // 2 + 1]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_correct_answer(question)["id"],
            }
        )
        score += 1

    response = await client.patch(
        f"/api/quizzes/update-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )
    assert response.status_code == 200
    data = response.json()

    assert data.keys() == {
        "id",
        "quiz_id",
        "user_id",
        "taker_name",
        "quiz_json",
        "answers_json",
        "started_at",
    }

    assert data["id"] == attempt_id
    assert data["quiz_id"] == quiz_id
    assert data["user_id"] == user["id"]
    assert data["taker_name"] == None
    # check_quiz_matches(data["quiz_json"], user, quiz, False)
    for i in range(len(answers)):
        assert answers[i]["question_id"] == data["answers_json"][i]["question_id"]
        assert answers[i]["answer_id"] == data["answers_json"][i]["answer_id"]


@pytest.mark.anyio
async def test_update_submitted_attempt_succesfully(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    get_correct_answer = lambda question: [
        answer for answer in question["answers"] if answer["is_correct"]
    ][0]

    get_wrong_answer = lambda question: [
        answer for answer in question["answers"] if not answer["is_correct"]
    ][0]

    answers = []
    score = 0
    for question in quiz["questions"][: len(quiz["questions"]) // 2 + 1]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_correct_answer(question)["id"],
            }
        )
        score += 1

    for question in quiz["questions"][len(quiz["questions"]) // 2 + 1 :]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_wrong_answer(question)["id"],
            }
        )

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    response = await client.patch(
        f"/api/quizzes/update-attempt/{attempt_id}",
        headers=auth_header(token),
    )

    assert response.status_code == 400
    assert response.json()["detail"] == QuizErrors.ATTEMPT_ALREADY_SUBMITTED


@pytest.mark.anyio
async def test_submit_attempt_with_grade_tiers(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    quiz["grade_tiers"] = {
        "A": 90,
        "B": 80,
        "C": 60,
        "F": 0,
    }
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    get_correct_answer = lambda question: [
        answer for answer in question["answers"] if answer["is_correct"]
    ][0]

    get_wrong_answer = lambda question: [
        answer for answer in question["answers"] if not answer["is_correct"]
    ][0]

    answers = []

    for question in quiz["questions"][: len(quiz["questions"]) // 2 + 1]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_correct_answer(question)["id"],
            }
        )

    for question in quiz["questions"][len(quiz["questions"]) // 2 + 1 :]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_wrong_answer(question)["id"],
            }
        )

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 2
    assert data["grade"] == "C"

    answers = []
    for question in quiz["questions"]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_correct_answer(question)["id"],
            }
        )

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 3
    assert data["grade"] == "A"

    answers = []
    for question in quiz["questions"]:
        answers.append(
            {
                "question_id": question["id"],
                "answer_id": get_wrong_answer(question)["id"],
            }
        )

    response = await client.post(
        f"/api/quizzes/{quiz_id}/start-attempt", headers=auth_header(token)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/submit-attempt/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 0
    assert data["grade"] == "F"
