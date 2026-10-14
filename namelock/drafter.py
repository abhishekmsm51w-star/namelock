"""Drafters turn a customer's messy message into a banner draft.

OllamaDrafter  - an open-weight model (Gemma by default) running locally via Ollama.
ScriptedDrafter - no model at all. It exists so the public demo and the tests can run
                  anywhere, and it can imitate a chat tool that "corrects" spellings.
                  It is always labelled as scripted in the UI.

Neither drafter is trusted. Whatever they return goes through lock.verify().
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field


class DraftError(RuntimeError):
    pass


@dataclass
class Draft:
    names: list[str]
    banner: str
    event: str | None = None
    size: str | None = None
    color: str | None = None
    backend: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


SYSTEM_PROMPT = """You prepare text for a flex banner print shop in India.
The customer sends a short, messy message in English, Hindi, Hinglish or a mix.

Return JSON only, with these keys:
- names: every person's name on the banner, copied EXACTLY as the customer typed it.
- event: the occasion, in English (birthday, wedding, engagement, ...), or null.
- size: banner size such as "6x3 ft", or null.
- color: background colour, or null.
- banner: the text to print on the banner.

Hard rules:
- Never correct, translate, transliterate, shorten or respell a name.
- If the customer says a spelling is wrong ("not Adya"), never use that spelling.
- Do not invent names, dates or phone numbers that are not in the message."""

SCHEMA = {
    "type": "object",
    "properties": {
        "names": {"type": "array", "items": {"type": "string"}},
        "event": {"type": ["string", "null"]},
        "size": {"type": ["string", "null"]},
        "color": {"type": ["string", "null"]},
        "banner": {"type": "string"},
    },
    "required": ["names", "banner"],
}


class OllamaDrafter:
    def __init__(
        self,
        model: str | None = None,
        host: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        self.model = model or os.environ.get("NAMELOCK_MODEL", "gemma3:4b")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.timeout = timeout

    @property
    def label(self) -> str:
        return f"{self.model} via Ollama (local)"

    def available(self) -> bool:
        try:
            with urllib.request.urlopen(self.host + "/api/tags", timeout=2) as r:
                tags = json.load(r)
        except (urllib.error.URLError, OSError, ValueError):
            return False
        names = {m.get("name") for m in tags.get("models", [])}
        return self.model in names or f"{self.model}:latest" in names

    def draft(self, note: str) -> Draft:
        body = json.dumps(
            {
                "model": self.model,
                "stream": False,
                "format": SCHEMA,
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": note},
                ],
            }
        ).encode()
        req = urllib.request.Request(
            self.host + "/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                reply = json.load(r)
            data = json.loads(reply["message"]["content"])
        except (urllib.error.URLError, OSError) as e:
            raise DraftError(f"Could not reach Ollama at {self.host}: {e}") from e
        except (KeyError, ValueError) as e:
            raise DraftError(f"The model did not return valid JSON: {e}") from e
        names = [str(n) for n in data.get("names") or [] if str(n).strip()]
        return Draft(
            names=names,
            banner=str(data.get("banner") or "").strip(),
            event=data.get("event"),
            size=data.get("size"),
            color=data.get("color"),
            backend=self.label,
        )


# What a chat tool tends to "fix". Used only by ScriptedDrafter(autocorrect=...).
AUTOCORRECT = {
    "Aadhya": "Adya",
    "Khushboo": "Khushbu",
    "D'souza": "Dsouza",
    "Siobhan": "Shivon",
    "Mohammed": "Muhammad",
    "Siddharth": "Sidharth",
    "Shreya": "Shriya",
    "Jyothi": "Jyoti",
    "Lakshmi": "Laxmi",
    "Aaradhya": "Aradhya",
    "Zo\u00eb": "Zoe",
    "Jos\u00e9": "Jose",
    "Priyanka": "Priyanca",
    "Aaliyah": "Aliya",
    "Vaibhav": "Vaibav",
    "Thejaswini": "Tejaswini",
    "Keerthana": "Kirthana",
    "Anushka": "Anuska",
    "Mary-Anne": "Maryann",
    "Dhanush": "Dhanus",
}

_NAME_RE = re.compile(
    r"\b(?:name|naam)\s*(?:is|:|-)?\s*"
    r"([A-Z\u00c0-\u00dd][\w'\u2019\-]*(?:\s+[A-Z\u00c0-\u00dd][\w'\u2019\-]*)?)"
)
_SIZE_RE = re.compile(r"(\d+)\s*(?:x|by|\*)\s*(\d+)", re.IGNORECASE)
_EVENTS = {
    "birthday": ("birthday", "janamdin", "janmadin", "b'day", "bday"),
    "wedding": ("wedding", "shaadi", "shadi", "marriage"),
    "engagement": ("engagement", "sagai"),
    "anniversary": ("anniversary",),
    "farewell": ("farewell",),
}
_COLORS = ("blue", "red", "green", "yellow", "pink", "white", "black", "orange", "purple")
_TEMPLATES = {
    "birthday": "Happy Birthday {n}",
    "wedding": "Wedding Celebration of {n}",
    "engagement": "Engagement Ceremony of {n}",
    "anniversary": "Happy Anniversary {n}",
    "farewell": "Farewell {n}",
}


@dataclass
class ScriptedDrafter:
    """No model. `autocorrect` imitates a chat tool that 'fixes' spellings:
    None   - copies the name faithfully
    "banner" - names are extracted correctly, then rewritten in the banner text
    "names"  - the extracted names themselves are rewritten
    """

    autocorrect: str | None = None
    label: str = field(default="scripted demo drafter (no model)", init=False)

    def available(self) -> bool:
        return True

    def draft(self, note: str) -> Draft:
        m = _NAME_RE.search(note)
        names = [m.group(1).strip()] if m else []
        low = note.lower()
        event = next((e for e, words in _EVENTS.items() if any(w in low for w in words)), None)
        sm = _SIZE_RE.search(note)
        color = next((c for c in _COLORS if c in low), None)

        banner_names = list(names)
        if self.autocorrect:
            banner_names = [AUTOCORRECT.get(n, n) for n in names]
        text = " & ".join(banner_names)
        template = _TEMPLATES.get(event or "", "{n}")
        banner = template.format(n=text) if text else ""
        if self.autocorrect == "names":
            names = banner_names
        return Draft(
            names=names,
            banner=banner,
            event=event,
            size=f"{sm.group(1)}x{sm.group(2)} ft" if sm else None,
            color=color,
            backend=self.label
            + (f" - imitating a tool that autocorrects ({self.autocorrect})" if self.autocorrect else ""),
        )
