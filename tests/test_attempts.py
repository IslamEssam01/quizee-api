import pytest
from httpx import AsyncClient

from tests.conftest import auth_header, create_test_user, login_user
from tests.test_quizzes import TestQuestion, check_quiz_matches, create_test_quiz
from utils.enums import GradingMode, QuestionType, Visibility
from utils.error_messages import QuizErrors


@pytest.mark.anyio
async def test_start_attempt_for_unknown_quiz(client: AsyncClient):
    response = await client.post(
        "/api/quizzes/999/attempts",
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
        f"/api/quizzes/{quiz_id}/attempts",
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
        f"/api/quizzes/{quiz_id}/attempts",
        headers=auth_header(token2),
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}

    check_quiz_matches(data["quiz"], user, quiz, True, exclude_keys={"owner"})


@pytest.mark.anyio
async def test_start_attempt_with_taker_name(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    quiz = await create_test_quiz(user)
    response = await client.post("/api/quizzes", json=quiz, headers=auth_header(token))
    data = response.json()
    quiz_id = data["id"]

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", json={"taker_name": "taker"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}
    check_quiz_matches(data["quiz"], user, quiz, True, exclude_keys={"owner"})


@pytest.mark.anyio
async def test_submit_unknown_attempt(client: AsyncClient):
    response = await client.post("/api/quizzes/attempts/submit/999")
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
    )
    data = response.json()
    attempt_id = data["id"]

    response = await client.post(
        f"/api/quizzes/attempts/submit/{attempt_id}", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
    )
    data = response.json()
    attempt_id = data["id"]

    await client.delete(f"/api/quizzes/{quiz_id}", headers=auth_header(token))

    response = await client.post(
        f"/api/quizzes/attempts/submit/{attempt_id}", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 5

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 2

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1.5

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()

    assert data["score"] == 1

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", json={"taker_name": "taker"}
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
    )

    assert response.status_code == 200

    response = await client.patch(
        f"/api/quizzes/{quiz_id}/update-access",
        json={"revoke_users": [user2["email"]]},
        headers=auth_header(token),
    )

    response = await client.post(
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
    )

    assert response.status_code == 403
    assert response.json()["detail"] == QuizErrors.NOT_AUTHORIZED_TO_TAKE_PRIVATE_QUIZ


@pytest.mark.anyio
async def test_resume_unknown_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.post(
        "/api/quizzes/attempts/resume/999", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/attempts/resume/{attempt_id}", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts",
        headers=auth_header(token2),
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/attempts/resume/{attempt_id}",
        headers=auth_header(token2),
    )

    assert response.status_code == 200
    data = response.json()
    assert data.keys() == {"id", "quiz"}

    check_quiz_matches(data["quiz"], user, quiz, True, exclude_keys={"owner"})


@pytest.mark.anyio
async def test_update_unknown_attempt(client: AsyncClient):
    user = await create_test_user(client)
    token, _ = await login_user(client)
    response = await client.patch(
        "/api/quizzes/attempts/999", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token2)
    )

    attempt_id = response.json()["id"]

    response = await client.patch(
        f"/api/quizzes/attempts/{attempt_id}", headers=auth_header(token)
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    response = await client.patch(
        f"/api/quizzes/attempts/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
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
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/attempts/submit/{attempt_id}",
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
        f"/api/quizzes/{quiz_id}/attempts", headers=auth_header(token)
    )

    attempt_id = response.json()["id"]

    response = await client.post(
        f"/api/quizzes/attempts/submit/{attempt_id}",
        json={"answers": answers},
        headers=auth_header(token),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["score"] == 0
    assert data["grade"] == "F"
