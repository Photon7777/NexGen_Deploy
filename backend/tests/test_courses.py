"""Phase 2a: course materials and "Ask your course" (chunk RAG)."""
import httpx
import openai
import pytest

from app import materials
from conftest import auth
from fakes import FakeExtractionModel, fake_embed
from pdfs import make_pdf


def page(*sentences: str, repeat: int = 6) -> list[str]:
    """About 1,000 characters of lecture text: the sentences, repeated like a dense slide deck."""
    return [s for _ in range(repeat) for s in sentences]


LECTURE_4 = make_pdf(
    page("Lecture 4: Linear regression.", "The least squares line minimizes the sum of squared residuals.",
         "The slope estimates the change in y for a one unit change in x."),
    page("Residual plots check the linearity assumption.", "A funnel shape in residuals signals heteroscedasticity,",
         "meaning the variance of the errors is not constant."),
    page("Logistic regression models the log odds of a binary outcome.",
         "Coefficients are read as changes in log odds, or as odds ratios after exponentiating."),
)
LECTURE_5 = make_pdf(page("Lecture 5: Decision trees split on the feature that most reduces Gini impurity.",
                          "Pruning limits depth to reduce overfitting."))

GROUNDED = {"covered": True, "answer": "It minimizes the sum of squared residuals [1].", "cited": [1]}


@pytest.fixture
def ai(client):
    """Swap in the stand-in embedder and a scripted answer model; returns the model to inspect."""
    from app.ai_deps import get_embedder, get_extraction_model
    from app.main import app

    model = FakeExtractionModel(GROUNDED)
    app.dependency_overrides[get_embedder] = lambda: fake_embed
    app.dependency_overrides[get_extraction_model] = lambda: model
    yield model
    app.dependency_overrides.pop(get_embedder, None)
    app.dependency_overrides.pop(get_extraction_model, None)


def new_course(client, user, name="BUDT 758T") -> str:
    return client.post("/courses", headers=auth(user), json={"name": name}).json()["id"]


def upload(client, user, course, content=LECTURE_4, name="lecture4.pdf"):
    return client.post(f"/courses/{course}/documents", headers=auth(user), files={"file": (name, content, "application/pdf")})


def ask(client, user, course, question="What does the least squares line minimize?"):
    return client.post(f"/courses/{course}/ask", headers=auth(user), json={"question": question})


# ------------------------------------------------------------------ chunking


def test_chunks_pack_lines_across_pages_and_record_the_pages():
    chunks = materials.chunk_pages(["alpha " * 20, "", "beta " * 20], size=300, overlap=0)
    assert [(c.page_from, c.page_to) for c in chunks] == [(1, 3)]  # the blank page adds nothing


def test_chunks_overlap_and_split_long_lines():
    lines = [f"Sentence number {i} about regression." for i in range(40)]
    chunks = materials.chunk_pages(["\n".join(lines)], size=400, overlap=80)
    assert len(chunks) > 3 and all(len(c.text) <= 400 + 80 for c in chunks)
    for before, after in zip(chunks, chunks[1:]):
        assert after.text.splitlines()[0] in before.text  # each chunk starts with the previous one's tail
    long = materials.chunk_pages(["word " * 500], size=300, overlap=0)
    assert len(long) > 5 and all(len(c.text) <= 300 for c in long)


def test_a_document_with_no_text_has_no_chunks():
    assert materials.chunk_pages(["", "  \n "]) == []


# ------------------------------------------------------------------ courses and uploads


def test_courses_are_created_once_per_course_code(client, make_user):
    user = make_user()
    first = client.post("/courses", headers=auth(user), json={"name": "BUDT 758T"})
    again = client.post("/courses", headers=auth(user), json={"name": "BUDT758T: Data Mining"})
    assert first.status_code == 201 and again.json()["id"] == first.json()["id"]
    assert client.get("/courses", headers=auth(user)).json() == [
        {"id": first.json()["id"], "name": "BUDT 758T", "documents": 0, "pages": 0, "assignments": 0}
    ]


def test_upload_keeps_pages_and_chunks(client, make_user, ai, admin_db):
    user = make_user()
    course = new_course(client, user)
    response = upload(client, user, course)
    assert response.status_code == 201
    doc = response.json()
    assert doc["filename"] == "lecture4.pdf" and doc["page_count"] == 3 and doc["chunks"] >= 2
    assert client.get(f"/courses/{course}/documents", headers=auth(user)).json()[0]["id"] == doc["id"]
    assert client.get("/courses", headers=auth(user)).json()[0]["pages"] == 3
    pages = admin_db.execute("select page_no, text from document_pages where document_id = %s order by page_no", (doc["id"],)).fetchall()
    assert [p[0] for p in pages] == [1, 2, 3] and "Logistic regression" in pages[2][1]


def test_the_same_file_twice_is_refused(client, make_user, ai):
    user = make_user()
    course = new_course(client, user)
    upload(client, user, course)
    response = upload(client, user, course, name="copy.pdf")
    assert response.status_code == 409


@pytest.mark.parametrize(
    "content, status",
    [(make_pdf([]), 422), (b"not a pdf at all", 422)],
    ids=["scan", "not-a-pdf"],
)
def test_unusable_files_are_refused(client, make_user, ai, content, status):
    user = make_user()
    assert upload(client, user, new_course(client, user), content).status_code == status


def test_page_limits_per_file_and_per_course(client, make_user, ai, monkeypatch):
    user = make_user()
    course = new_course(client, user)
    monkeypatch.setattr(materials, "MAX_DOCUMENT_PAGES", 2)
    assert upload(client, user, course).status_code == 413  # three pages
    monkeypatch.setattr(materials, "MAX_DOCUMENT_PAGES", 300)
    monkeypatch.setattr(materials, "MAX_COURSE_PAGES", 3)
    assert upload(client, user, course).status_code == 201
    assert upload(client, user, course, LECTURE_5, "lecture5.pdf").status_code == 413


def test_deleting_a_document_removes_its_chunks(client, make_user, ai, admin_db):
    user = make_user()
    course = new_course(client, user)
    doc = upload(client, user, course).json()
    assert client.delete(f"/documents/{doc['id']}", headers=auth(user)).status_code == 204
    assert admin_db.execute("select count(*) from chunks where document_id = %s", (doc["id"],)).fetchone()[0] == 0
    assert ask(client, user, course).status_code == 409


# ------------------------------------------------------------------ ask


def test_ask_answers_from_the_closest_chunks_and_cites_them(client, make_user, ai, admin_db):
    user = make_user()
    course = new_course(client, user)
    upload(client, user, course)
    upload(client, user, course, LECTURE_5, "lecture5.pdf")

    response = ask(client, user, course)
    assert response.status_code == 200
    body = response.json()
    assert body["covered"] and body["answer"] == GROUNDED["answer"]
    [cite] = body["citations"]
    assert cite["n"] == 1 and cite["filename"] == "lecture4.pdf" and cite["page_from"] == 1
    assert "least squares line minimizes" in cite["text"]
    assert "[1] lecture4.pdf, page" in ai.prompts[0]  # the closest chunk is source 1

    row = admin_db.execute(
        "select approach, covered, tokens, jsonb_array_length(retrieved) n from course_questions where course_id = %s", (course,)
    ).fetchone()
    assert row == ("chunks", True, 1000, len(ai.prompts[0].split("\n\n[")))
    assert admin_db.execute("select count(*) from ai_requests where user_id = %s and kind = 'ask'", (user,)).fetchone()[0] == 1
    history = client.get(f"/courses/{course}/questions", headers=auth(user)).json()
    assert history[0]["question"] == "What does the least squares line minimize?"
    assert history[0]["citations"][0]["filename"] == "lecture4.pdf"


def test_ask_without_materials_does_not_use_the_quota(client, make_user, ai, admin_db):
    user = make_user()
    assert ask(client, user, new_course(client, user)).status_code == 409
    assert admin_db.execute("select count(*) from ai_requests where user_id = %s", (user,)).fetchone()[0] == 0


def test_citations_ignore_sources_that_do_not_exist_and_uncovered_answers(client, make_user, ai):
    user = make_user()
    course = new_course(client, user)
    upload(client, user, course)
    ai.result = {"covered": True, "answer": "See [2] and [9].", "cited": [9]}
    assert [c["n"] for c in ask(client, user, course).json()["citations"]] == [2]
    ai.result = {"covered": False, "answer": "The materials cover regression and trees, not neural networks.", "cited": []}
    body = ask(client, user, course, "How does backpropagation work?").json()
    assert body["covered"] is False and body["citations"] == []


def test_an_embedding_failure_is_a_readable_502(client, make_user, ai):
    from app.ai_deps import get_embedder
    from app.main import app

    user = make_user()
    course = new_course(client, user)

    def broken(texts):
        raise openai.APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"))

    app.dependency_overrides[get_embedder] = lambda: broken
    response = upload(client, user, course)
    assert response.status_code == 502 and "Could not reach OpenAI" in response.json()["detail"]
    assert client.get(f"/courses/{course}/documents", headers=auth(user)).json() == []


def test_materials_and_questions_are_private(client, make_user, ai):
    owner, other = make_user(), make_user()
    course = new_course(client, owner)
    doc = upload(client, owner, course).json()
    assert client.get(f"/courses/{course}/documents", headers=auth(other)).status_code == 404
    assert ask(client, other, course).status_code == 404
    assert client.delete(f"/documents/{doc['id']}", headers=auth(other)).status_code == 404
    assert upload(client, other, course, LECTURE_5, "x.pdf").status_code == 404
    assert client.get("/courses", headers=auth(other)).json() == []
