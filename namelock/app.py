"""Web app. The server, not the browser, decides whether a banner can print."""

from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from .book import open_book
from .drafter import DraftError, OllamaDrafter, ScriptedDrafter
from .lock import verify

STATIC = Path(__file__).resolve().parent.parent / "static"


def _load_env() -> None:
    path = STATIC.parent / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


_load_env()

# NAMELOCK_BACKEND=ollama (default, real model on this machine) | demo (no model, sample notes)
DEMO = os.environ.get("NAMELOCK_BACKEND", "ollama").lower() == "demo"

app = FastAPI(title="NameLock")
book = open_book(demo=DEMO)
ollama = OllamaDrafter()

SAMPLES = [
    {
        "label": "Two a's, not Adya",
        "note": "blue flex 6 by 3, birthday, name Aadhya, with two a's, not Adya",
    },
    {"label": "Hinglish, Khushboo", "note": "bhaiya birthday ka banner chahiye 6x3 red, naam Khushboo likhna"},
    {"label": "Accent, Jos\u00e9", "note": "wedding banner 8x4 pink, name Jos\u00e9"},
    {"label": "Apostrophe, D'souza", "note": "need a 4x2 green flex for engagement, name D'souza"},
]


class Order(BaseModel):
    note: str
    names: list[str]
    banner: str


class DraftRequest(BaseModel):
    note: str
    autocorrect: str | None = None  # demo mode only: imitate a tool that fixes spellings


class Approve(BaseModel):
    name: str


def _verdict(o: Order):
    return verify(o.note, o.names, o.banner, approved=book.names())


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status():
    if DEMO:
        return {
            "mode": "demo",
            "drafter": ScriptedDrafter().label,
            "model_ready": False,
            "samples": SAMPLES,
            "note": "Public demo: scripted drafter, sample notes only. Real messages stay on the shop laptop.",
        }
    return {
        "mode": "local",
        "drafter": ollama.label,
        "model_ready": ollama.available(),
        "samples": SAMPLES,
    }


@app.post("/api/draft")
def draft(req: DraftRequest):
    note = req.note.strip()
    if not note:
        raise HTTPException(400, "Paste the customer's message first.")
    if DEMO:
        auto = req.autocorrect if req.autocorrect in ("banner", "names") else None
        d = ScriptedDrafter(autocorrect=auto).draft(note)
    else:
        try:
            d = ollama.draft(note)
        except DraftError as e:
            raise HTTPException(502, str(e)) from e
    v = verify(note, d.names, d.banner, approved=book.names())
    return {"draft": d.to_dict(), "verdict": v.to_dict()}


@app.post("/api/verify")
def verify_order(o: Order):
    return _verdict(o).to_dict()


@app.post("/api/approve")
def approve(a: Approve):
    if not a.name.strip():
        raise HTTPException(400, "Nothing to approve.")
    book.approve(a.name)
    return {"approved": book.names()}


@app.get("/api/book")
def get_book():
    return {"approved": book.names()}


@app.post("/api/print", response_class=HTMLResponse)
def print_page(o: Order):
    v = _verdict(o)
    if not v.printable:
        raise HTTPException(409, "Not printable: " + "; ".join(i.message for i in v.issues))
    # Anything that prints has just passed the lock, and every printed name is remembered.
    for n in v.names:
        book.approve(n)
    text = html.escape(o.banner)
    return (
        "<!doctype html><meta charset=utf-8><title>Banner</title>"
        "<style>@page{size:landscape;margin:12mm}body{margin:0;display:grid;place-items:center;"
        "min-height:100vh;font:700 9vw/1.1 system-ui,sans-serif;text-align:center}</style>"
        f"<body><div>{text}</div><script>addEventListener('load',()=>print())</script>"
    )
