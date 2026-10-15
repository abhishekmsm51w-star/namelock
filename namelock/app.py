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

# NAMELOCK_BACKEND=ollama (default, real model on this machine) | demo (no model, sample notes).
# Render always sets RENDER=true. The public host must never call Ollama.
DEMO = os.environ.get("NAMELOCK_BACKEND", "ollama").lower() == "demo" or bool(
    os.environ.get("RENDER")
)

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
    return _print_html(o.banner, v.names)


PRINT_CSS = """
@page{size:landscape;margin:10mm}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:#14110e;color:#f6f1e8;font:16px/1.4 "Segoe UI",Arial,sans-serif;
  display:flex;flex-direction:column;align-items:center}
.bar{width:100%;display:flex;gap:14px;align-items:center;justify-content:space-between;flex-wrap:wrap;
  padding:14px 22px;border-bottom:1px solid rgba(255,255,255,.1);background:#1b1713}
.ok{display:flex;gap:10px;align-items:center}
.tick{width:30px;height:30px;border-radius:50%;background:#2f9e5b;color:#fff;display:grid;place-items:center;font-weight:700}
.ok b{display:block}.ok span{color:#c9bfb2;font-size:14px}
.go{font:700 16px/1 "Segoe UI",Arial,sans-serif;padding:13px 22px;border-radius:999px;border:1px solid #111;
  background:#ffe34a;color:#1c1915;cursor:pointer}
.stage{flex:1;width:100%;display:grid;place-items:center;padding:30px 18px}
.crop{position:relative;width:min(1000px,94vw);padding:26px}
.crop::before,.crop::after,.crop i::before,.crop i::after{content:"";position:absolute;width:20px;height:20px;border:0 solid #8d8478}
.crop::before{top:0;left:0;border-width:1px 0 0 1px}
.crop::after{top:0;right:0;border-width:1px 1px 0 0}
.crop i::before{bottom:0;left:0;border-width:0 0 1px 1px}
.crop i::after{bottom:0;right:0;border-width:0 1px 1px 0}
.sheet{position:relative;width:100%;aspect-ratio:2/1;background:
  linear-gradient(180deg,rgba(255,255,255,.4),transparent 28%),
  repeating-linear-gradient(90deg,rgba(0,0,0,.03) 0 1px,transparent 1px 8px),#ffe34a;
  color:#16140f;display:grid;place-items:center;text-align:center;overflow:hidden;
  box-shadow:0 26px 50px rgba(0,0,0,.5);-webkit-print-color-adjust:exact;print-color-adjust:exact}
.sheet::before{content:"";position:absolute;inset:16px;border:3px solid #16140f;pointer-events:none}
.text{width:78%;font:700 120px/1.02 "Barlow Condensed","Arial Narrow",Impact,sans-serif;letter-spacing:.03em;
  text-transform:uppercase}
.g{position:absolute;width:22px;height:22px;border-radius:50%;
  background:radial-gradient(circle at 35% 35%,#fff,#9a9a9a 42%,#2c2c2c 72%);box-shadow:0 0 0 4px #2a2a2a}
.g1{top:30px;left:30px}.g2{top:30px;right:30px}.g3{bottom:30px;left:30px}.g4{bottom:30px;right:30px}
.foot{margin-top:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;color:#b7ad9f;
  font:12px/1.3 ui-monospace,Consolas,monospace;letter-spacing:.06em;text-transform:uppercase}
@media print{
  body{background:#fff;color:#000;display:block}
  .bar,.foot{display:none}
  .stage{padding:0;display:block}
  .crop{width:100%;padding:8mm}
  .sheet{box-shadow:none}
}
"""

PRINT_JS = """
const t=document.getElementById('t'),s=document.getElementById('s');
function fit(){let n=260;t.style.fontSize=n+'px';
  const w=s.clientWidth*.78,h=s.clientWidth*.5*.62;
  while((t.scrollWidth>w||t.offsetHeight>h)&&n>14){n-=4;t.style.fontSize=n+'px'}}
addEventListener('load',fit);addEventListener('resize',fit);addEventListener('beforeprint',fit);
if(document.fonts)document.fonts.ready.then(fit);
document.getElementById('go').onclick=()=>print();
"""


def _print_html(banner: str, names: list[str]) -> str:
    text = html.escape(banner)
    checked = html.escape(", ".join(names)) or "none"
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'><title>Banner proof</title>"
        "<link rel=preconnect href=https://fonts.googleapis.com>"
        "<link href='https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&display=swap' rel=stylesheet>"
        f"<style>{PRINT_CSS}</style></head><body>"
        "<div class=bar><div class=ok><div class=tick>&#10003;</div>"
        f"<div><b>Proof passed</b><span>Names checked against the customer's message: {checked}</span></div></div>"
        "<button class=go id=go>Print banner</button></div>"
        "<div class=stage><div class=crop><i></i>"
        "<div class=sheet id=s><span class='g g1'></span><span class='g g2'></span>"
        "<span class='g g3'></span><span class='g g4'></span>"
        f"<div class=text id=t>{text}</div></div>"
        "<div class=foot><span>NameLock proof</span><span>Check the spelling once more on paper</span></div>"
        "</div></div>"
        f"<script>{PRINT_JS}</script></body></html>"
    )
