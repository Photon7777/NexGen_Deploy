"""Phase 0b endpoints: planner, calendar export, agent chat, flashcards, check-ins, CSV import."""
from datetime import datetime

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage, HumanMessage

from conftest import auth
from fakes import FakeFlashcardModel, FakeToolModel
from nexlearn.data import template_csv


@pytest.fixture
def use_model(client):
    from app.ai_deps import get_chat_model
    from app.main import app

    def _use(model):
        app.dependency_overrides[get_chat_model] = lambda: model

    yield _use
    app.dependency_overrides.pop(get_chat_model, None)


@pytest.fixture
def limits(client):
    from app.config import get_settings
    from app.main import app

    def _set(per_user: int, total: int = 1000):
        settings = get_settings().model_copy(update={"ai_requests_per_user_per_day": per_user, "ai_requests_per_day": total})
        app.dependency_overrides[get_settings] = lambda: settings

    yield _set
    app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def student(client, make_user):
    """A student with the six sample assignments loaded."""
    user = make_user()
    client.post("/assignments/sample", headers=auth(user))
    return user


def _by_title(client, user):
    return {a["title"]: a for a in client.get("/assignments", headers=auth(user)).json()}


# ------------------------------------------------------------------ assignments and planner


def test_assignments_carry_planning_fields(client, student):
    quiz = _by_title(client, student)["Global Markets Quiz"]
    assert quiz["remaining_hours"] == quiz["hours_required"] == 2
    # Due at 11:59 PM tomorrow: between 1 and 2 days away, depending on the time of day.
    assert 0 < quiz["days_left"] <= 2 and quiz["priority"] > 0 and quiz["overdue"] is False


def test_plan_is_saved_replaced_and_never_overlaps(client, student, admin_db):
    plan = client.post("/plan", headers=auth(student), json={"daily_cap_hours": 3}).json()
    blocks = plan["blocks"]
    assert blocks
    spans = [(datetime.fromisoformat(b["starts_at"]), datetime.fromisoformat(b["ends_at"])) for b in blocks]
    assert all(s < e for s, e in spans)
    assert all(e1 <= s2 for (_, e1), (s2, _) in zip(spans, spans[1:])), "blocks overlap"

    again = client.post("/plan", headers=auth(student), json={"daily_cap_hours": 1}).json()
    stored = admin_db.execute(
        "select count(*) from study_blocks where user_id = %s and ends_at > now()", (student,)
    ).fetchone()[0]
    assert stored == len(again["blocks"]) == len(client.get("/plan", headers=auth(student)).json()["blocks"])


def test_finished_work_is_left_out_of_the_plan(client, student):
    quiz = _by_title(client, student)["Global Markets Quiz"]
    client.patch(f"/assignments/{quiz['id']}", headers=auth(student), json={"completion_pct": 100})
    blocks = client.post("/plan", headers=auth(student), json={}).json()["blocks"]
    assert blocks and "Global Markets Quiz" not in {b["title"] for b in blocks}


def test_plan_window_must_be_open(client, student):
    assert client.post("/plan", headers=auth(student), json={"start_hour": 18, "end_hour": 9}).status_code == 422


def test_plan_downloads_as_ics(client, student):
    n = len(client.post("/plan", headers=auth(student), json={}).json()["blocks"])
    res = client.get("/plan/ics", headers=auth(student))
    assert res.headers["content-type"].startswith("text/calendar")
    assert "attachment" in res.headers["content-disposition"]
    assert res.text.count("BEGIN:VEVENT") == n > 0


def test_students_plans_are_private(client, student, make_user):
    client.post("/plan", headers=auth(student), json={})
    assert client.get("/plan", headers=auth(make_user())).json()["blocks"] == []


# ------------------------------------------------------------------ agent chat


def test_chat_is_off_without_an_api_key(client, student):
    assert client.post("/chat", headers=auth(student), json={"message": "hi"}).status_code == 503


def test_agent_updates_progress_plans_and_remembers(client, student, use_model, admin_db):
    model = FakeToolModel(messages=iter([
        AIMessage(content="", tool_calls=[
            {"name": "update_progress", "args": {"assignment": "Data Analytics Midterm", "percent_complete": 50}, "id": "c1"},
            {"name": "plan_study_week", "args": {}, "id": "c2"},
        ]),
        AIMessage(content="Marked the midterm 50% done and planned your week."),
    ]))
    use_model(model)
    body = client.post("/chat", headers=auth(student), json={"message": "I'm halfway through the midterm prep"}).json()

    assert body == {
        "reply": "Marked the midterm 50% done and planned your week.",
        "plan_updated": True,
        "progress_updated": ["Data Analytics Midterm"],
    }
    assert _by_title(client, student)["Data Analytics Midterm"]["completion_pct"] == 50
    assert admin_db.execute(
        "select changed_by from progress_events where user_id = %s", (student,)
    ).fetchall() == [("agent",)]
    assert client.get("/plan", headers=auth(student)).json()["blocks"]

    # The next turn sends the saved conversation back to the model.
    follow_up = FakeToolModel(messages=iter([AIMessage(content="You said you were halfway.")]))
    use_model(follow_up)
    client.post("/chat", headers=auth(student), json={"message": "What did I tell you?"})
    sent = follow_up.seen[0]
    assert any(isinstance(m, HumanMessage) and "halfway through the midterm" in m.content for m in sent)
    assert [m["role"] for m in client.get("/chat", headers=auth(student)).json()] == ["user", "assistant"] * 2

    assert client.delete("/chat", headers=auth(student)).status_code == 204
    assert client.get("/chat", headers=auth(student)).json() == []


# ------------------------------------------------------------------ flashcards and usage caps


def test_flashcards_return_the_requested_count(client, student, use_model):
    use_model(FakeFlashcardModel())
    cards = client.post("/flashcards", headers=auth(student), json={"topic": "SQL window functions", "count": 4}).json()
    assert [c["question"] for c in cards] == ["Q1", "Q2", "Q3", "Q4"]


def test_daily_cap_refuses_the_request_over_the_limit(client, make_user, use_model, limits):
    use_model(FakeFlashcardModel())
    limits(per_user=2)
    user = make_user()
    codes = [client.post("/flashcards", headers=auth(user), json={"topic": "regression"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    other = make_user()
    assert client.post("/flashcards", headers=auth(other), json={"topic": "regression"}).status_code == 200


def test_openai_errors_become_clear_messages(client, student, use_model):
    response = httpx.Response(401, request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"))
    use_model(FakeFlashcardModel(error=openai.AuthenticationError("bad key", response=response, body=None)))
    res = client.post("/flashcards", headers=auth(student), json={"topic": "regression"})
    assert res.status_code == 502 and "OPENAI_API_KEY" in res.json()["detail"]


# ------------------------------------------------------------------ check-ins and CSV import


def test_checkins_round_trip_and_stay_private(client, student, make_user):
    created = client.post("/checkins", headers=auth(student), json={"mood": 4, "energy": 3, "confidence": 5, "note": " ok "})
    assert created.status_code == 201 and created.json()["note"] == "ok"
    assert len(client.get("/checkins", headers=auth(student)).json()) == 1
    assert client.get("/checkins", headers=auth(make_user())).json() == []
    assert client.post("/checkins", headers=auth(student), json={"mood": 6, "energy": 3, "confidence": 3}).status_code == 422


def test_csv_import_adds_then_updates_without_duplicates(client, make_user):
    user = make_user()
    files = {"file": ("syllabus.csv", template_csv(), "text/csv")}
    first = client.post("/assignments/import", headers=auth(user), files=files).json()
    second = client.post("/assignments/import", headers=auth(user), files=files).json()
    assert first["imported"] == second["imported"] == 2
    assert len(second["assignments"]) == 2
    bad = client.post("/assignments/import", headers=auth(user), files={"file": ("x.csv", b"Title,Due\nx,y\n", "text/csv")})
    assert bad.status_code == 422 and "Course" in bad.json()["detail"]
