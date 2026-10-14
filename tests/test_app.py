import os

os.environ["NAMELOCK_BACKEND"] = "demo"  # before importing the app: no model, in-memory book

from fastapi.testclient import TestClient  # noqa: E402

from namelock.app import app  # noqa: E402

client = TestClient(app)
NOTE = "blue flex 6 by 3, birthday, name Aadhya, with two a's, not Adya"


def test_status_says_demo_and_scripted():
    s = client.get("/api/status").json()
    assert s["mode"] == "demo"
    assert "scripted" in s["drafter"]


def test_faithful_draft_is_printable():
    r = client.post("/api/draft", json={"note": NOTE}).json()
    assert r["draft"]["names"] == ["Aadhya"]
    assert r["verdict"]["printable"] is True


def test_autocorrecting_tool_is_stopped_and_repair_offered():
    r = client.post("/api/draft", json={"note": NOTE, "autocorrect": "banner"}).json()
    assert "Adya" in r["draft"]["banner"]
    assert r["verdict"]["printable"] is False
    assert r["verdict"]["fixed_banner"] == "Happy Birthday Aadhya"


def test_print_endpoint_refuses_a_changed_name_even_if_the_page_is_bypassed():
    r = client.post(
        "/api/print", json={"note": NOTE, "names": ["Aadhya"], "banner": "Happy Birthday Adya"}
    )
    assert r.status_code == 409
    assert "Adya" in r.text


def test_print_endpoint_prints_a_good_banner_and_escapes_html():
    r = client.post(
        "/api/print",
        json={"note": "name Aadhya", "names": ["Aadhya"], "banner": "<b>Aadhya</b>"},
    )
    assert r.status_code == 200
    assert "&lt;b&gt;Aadhya&lt;/b&gt;" in r.text


def test_printing_remembers_the_name_and_a_near_miss_then_needs_confirmation():
    ok = client.post(
        "/api/print", json={"note": "name Priyanka", "names": ["Priyanka"], "banner": "Priyanka"}
    )
    assert ok.status_code == 200
    assert "Priyanka" in client.get("/api/book").json()["approved"]
    v = client.post(
        "/api/verify", json={"note": "name Priyanca", "names": ["Priyanca"], "banner": "Priyanca"}
    ).json()
    assert v["printable"] is False
    assert v["issues"][0]["kind"] == "confirm_book"
    client.post("/api/approve", json={"name": "Priyanca"})
    v = client.post(
        "/api/verify", json={"note": "name Priyanca", "names": ["Priyanca"], "banner": "Priyanca"}
    ).json()
    assert v["printable"] is True


def test_empty_note_is_rejected():
    assert client.post("/api/draft", json={"note": "  "}).status_code == 400
