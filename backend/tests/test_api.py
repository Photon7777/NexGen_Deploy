from datetime import datetime, timedelta, timezone

import pytest

from conftest import auth, make_token

LATER = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "header",
    [
        None,
        "Bearer not-a-jwt",
        f"Bearer {make_token('00000000-0000-0000-0000-000000000001', secret='a-different-secret-that-is-also-long-enough')}",
        f"Bearer {make_token('00000000-0000-0000-0000-000000000001', expires_in=-60)}",
        f"Bearer {make_token('00000000-0000-0000-0000-000000000001', aud='anon')}",
    ],
    ids=["missing", "garbage", "wrong-signature", "expired", "wrong-audience"],
)
def test_bad_or_missing_tokens_are_rejected(client, header):
    headers = {"Authorization": header} if header else {}
    assert client.get("/assignments", headers=headers).status_code == 401


def test_a_connection_the_database_dropped_is_replaced_not_reused(client, make_user, admin_db):
    # Supabase's pooler closes idle connections. On Cloud Run this surfaced as a 500
    # ("SSL error: unexpected eof") on the first request after a quiet spell.
    user = make_user()
    assert client.get("/assignments", headers=auth(user)).status_code == 200
    admin_db.execute(
        "select pg_terminate_backend(pid) from pg_stat_activity"
        " where datname = current_database() and backend_type = 'client backend' and pid <> pg_backend_pid()"
    )
    assert client.get("/assignments", headers=auth(user)).status_code == 200


def test_me_returns_the_profile_the_signup_trigger_created(client, make_user):
    user = make_user("Terry Terp")
    body = client.get("/me", headers=auth(user)).json()
    assert body["display_name"] == "Terry Terp"
    assert body["timezone"] == "America/New_York"


def test_sample_assignments_are_upcoming_and_reloading_does_not_duplicate(client, make_user):
    user = make_user()
    first = client.post("/assignments/sample", headers=auth(user)).json()
    again = client.post("/assignments/sample", headers=auth(user)).json()
    assert len(first) == len(again) == 6
    due = [datetime.fromisoformat(a["due_at"]) for a in first]
    assert due == sorted(due) and due[0] > datetime.now(timezone.utc)
    assert {a["source"] for a in first} == {"sample"}


def test_students_cannot_see_or_change_each_others_assignments(client, make_user):
    alice, bob = make_user("Alice"), make_user("Bob")
    created = client.post(
        "/assignments", headers=auth(alice), json={"title": "Essay", "course": "BMGT 340", "due_at": LATER, "hours_required": 3}
    ).json()

    assert client.get("/assignments", headers=auth(bob)).json() == []
    assert client.patch(f"/assignments/{created['id']}", headers=auth(bob), json={"completion_pct": 100}).status_code == 404
    assert client.delete(f"/assignments/{created['id']}", headers=auth(bob)).status_code == 404
    assert client.get("/assignments", headers=auth(alice)).json()[0]["completion_pct"] == 0


def test_create_update_delete_records_progress_history(client, make_user, admin_db):
    user = make_user()
    a = client.post(
        "/assignments", headers=auth(user), json={"title": "Case write-up", "course": "BUDT 704", "due_at": LATER, "hours_required": 4}
    ).json()
    assert a["course"] == "BUDT 704" and a["completion_pct"] == 0

    updated = client.patch(f"/assignments/{a['id']}", headers=auth(user), json={"completion_pct": 40, "title": None}).json()
    assert updated["completion_pct"] == 40 and updated["title"] == "Case write-up"
    client.patch(f"/assignments/{a['id']}", headers=auth(user), json={"completion_pct": 40})  # unchanged: no event
    events = admin_db.execute(
        "select completion_pct, changed_by from progress_events where assignment_id = %s", (a["id"],)
    ).fetchall()
    assert events == [(40, "student")]

    assert client.patch(f"/assignments/{a['id']}", headers=auth(user), json={"course": None}).json()["course"] is None
    assert client.delete(f"/assignments/{a['id']}", headers=auth(user)).status_code == 204
    assert client.get("/assignments", headers=auth(user)).json() == []


@pytest.mark.parametrize(
    "body",
    [
        {"title": "", "due_at": LATER, "hours_required": 1},
        {"title": "X", "due_at": LATER, "hours_required": -1},
        {"title": "X", "due_at": "2026-11-04T17:00:00", "hours_required": 1},  # no time zone
    ],
    ids=["empty-title", "negative-hours", "naive-datetime"],
)
def test_invalid_assignments_are_rejected(client, make_user, body):
    assert client.post("/assignments", headers=auth(make_user()), json=body).status_code == 422


def test_rls_blocks_cross_user_reads_even_in_raw_sql(client, make_user, database_url):
    """The API's own guard is the database policy, not a WHERE clause in Python."""
    import psycopg

    from app.auth import User
    from app.db import user_transaction

    alice, bob = make_user(), make_user()
    client.post("/assignments/sample", headers=auth(alice))
    with user_transaction(User(bob, None, {"sub": bob, "role": "authenticated"})) as conn:
        assert conn.execute("select count(*) as n from assignments").fetchone()["n"] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conn.execute("insert into assignments (user_id, title, due_at, hours_required) values (%s, 'x', now(), 1)", (alice,))
