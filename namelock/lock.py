"""The spelling lock.

A model may draft a banner line. It may not change a person's name.

`verify()` is the only gate between a draft and the print button. It is plain
Python (no model), so it behaves the same whichever model produced the draft.

Rules, in order, for every name the draft claims to contain:

1. The customer said NOT this spelling ("Aadhya, not Adya")  -> block
2. The name is not in the customer's own note                 -> block
3. The name is missing from the banner                        -> block
   (and if the banner has a near-miss spelling, say which one and offer the fix)
4. The banner carries a forbidden spelling                    -> block
5. The note's spelling is close to, but not the same as, a spelling the shop
   already approved                                           -> confirm

A banner is printable only when there are no issues of either severity.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher, get_close_matches
from typing import Iterable

TOKEN_RE = re.compile(r"[^\W\d_][\w'\u2019\-]*")
NEAR_MISS = 0.75  # banner word this similar to a name, but not equal -> respelled
NEAR_BOOK = 0.80  # note name this similar to an approved name, but not equal -> confirm

BLOCK = "block"
CONFIRM = "confirm"


def norm(text: str) -> str:
    """NFC only. Never strip accents: Jose is not Jose-with-an-accent."""
    return unicodedata.normalize("NFC", text)


def key(text: str) -> str:
    return norm(text).casefold()


def _tokens(text: str) -> list[tuple[str, int, int]]:
    """(word, start, end) over norm(text). Possessive 's is not part of the name."""
    out: list[tuple[str, int, int]] = []
    for m in TOKEN_RE.finditer(norm(text)):
        word = m.group().rstrip("'\u2019-")
        end = m.start() + len(word)
        if len(word) > 3 and word.lower().endswith(("'s", "\u2019s")):
            word, end = word[:-2], end - 2
        if word:
            out.append((word, m.start(), end))
    return out


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    parts = [re.escape(p) for p in norm(phrase).split()]
    return re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)", re.IGNORECASE)


def _find(text: str, phrase: str) -> str | None:
    """The exact text of `phrase` as it appears in `text` (ignoring case only)."""
    if not phrase.strip():
        return None
    m = _phrase_pattern(phrase).search(norm(text))
    return m.group() if m else None


def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, key(a), key(b)).ratio()


_NOT_RE = re.compile(r"\b[Nn][Oo][Tt]\s+(?:spelled\s+|spelt\s+|written\s+)?([^\W\d_][\w'\u2019\-]*)")


def forbidden_spellings(note: str) -> set[str]:
    """Spellings the customer explicitly rejected: 'Aadhya, not Adya' -> {'adya'}.

    Only capitalised words count, so 'not too big' does not forbid 'too'.
    """
    out: set[str] = set()
    for m in _NOT_RE.finditer(norm(note)):
        word = m.group(1).rstrip("'\u2019-")
        if word[:1].isupper():
            out.add(key(word))
    return out


@dataclass
class Issue:
    kind: str
    severity: str  # "block" | "confirm"
    name: str
    message: str
    found: str | None = None  # what the banner/draft has instead
    suggestion: str | None = None  # the spelling from the customer's own note
    span: tuple[int, int] | None = field(default=None, repr=False)


@dataclass
class Verdict:
    printable: bool
    names: list[str]
    issues: list[Issue]
    fixed_banner: str | None  # banner with the customer's spelling restored, if we can

    def to_dict(self) -> dict:
        d = asdict(self)
        for issue in d["issues"]:
            issue.pop("span", None)
        return d


def verify(
    note: str,
    names: Iterable[str],
    banner: str,
    approved: Iterable[str] = (),
) -> Verdict:
    names = [n.strip() for n in names if n and n.strip()]
    banner_n = norm(banner)
    banner_tokens = _tokens(banner_n)
    banner_keys = {key(t) for t, _, _ in banner_tokens}
    name_keys = {key(n) for n in names}
    forbidden = forbidden_spellings(note) - name_keys
    approved = list(approved)
    issues: list[Issue] = []

    if not names:
        issues.append(
            Issue(
                "no_name",
                CONFIRM,
                "",
                "No name was found in this order. Type the name exactly as the customer wrote it.",
            )
        )

    for name in names:
        asked = norm(name)

        # 1. the customer rejected this very spelling
        if key(asked) in forbidden_spellings(note):
            issues.append(
                Issue(
                    "forbidden_spelling",
                    BLOCK,
                    asked,
                    f"The customer wrote NOT {asked}. That spelling must not be printed.",
                    found=asked,
                )
            )
            continue

        # 2. the model's name has to be in the customer's own words
        in_note = _find(note, asked)
        if in_note is None:
            note_words = [t for t, _, _ in _tokens(note)]
            close = get_close_matches(asked, note_words, n=1, cutoff=0.6)
            issues.append(
                Issue(
                    "not_in_note",
                    BLOCK,
                    asked,
                    f"'{asked}' is not in the customer's message."
                    + (f" Their message has '{close[0]}'." if close else ""),
                    found=asked,
                    suggestion=close[0] if close else None,
                )
            )
            continue

        # 3. the name has to reach the banner untouched
        if _find(banner_n, in_note) is None:
            n_words = len(in_note.split())
            best: tuple[float, str, int, int] | None = None
            for i in range(len(banner_tokens) - n_words + 1):
                window = banner_tokens[i : i + n_words]
                cand = " ".join(t for t, _, _ in window)
                if key(cand) == key(in_note) or key(cand) in name_keys:
                    continue
                r = _ratio(cand, in_note)
                if r >= NEAR_MISS and (best is None or r > best[0]):
                    best = (r, cand, window[0][1], window[-1][2])
            if best is not None:
                issues.append(
                    Issue(
                        "respelled",
                        BLOCK,
                        in_note,
                        f"The banner says '{best[1]}'. The customer wrote '{in_note}'.",
                        found=best[1],
                        suggestion=in_note,
                        span=(best[2], best[3]),
                    )
                )
            else:
                issues.append(
                    Issue(
                        "missing_from_banner",
                        BLOCK,
                        in_note,
                        f"'{in_note}' is not on the banner.",
                        suggestion=in_note,
                    )
                )

        # 5. close to a spelling the shop already approved, but not the same
        if approved and not any(key(a) == key(in_note) for a in approved):
            near = [a for a in approved if _ratio(a, in_note) >= NEAR_BOOK]
            if near:
                issues.append(
                    Issue(
                        "confirm_book",
                        CONFIRM,
                        in_note,
                        f"Your approved spelling is '{near[0]}'. This order says '{in_note}'. "
                        "Confirm this is a different person, or ask the customer.",
                        found=in_note,
                        suggestion=near[0],
                    )
                )

    # 4. a spelling the customer rejected must not appear on the banner
    already = {i.span for i in issues if i.kind == "respelled" and i.span}
    for word, start, end in banner_tokens:
        if key(word) in forbidden and (start, end) not in already:
            issues.append(
                Issue(
                    "forbidden_spelling",
                    BLOCK,
                    word,
                    f"The banner has '{word}'. The customer wrote NOT {word}.",
                    found=word,
                    span=(start, end),
                )
            )

    fixes = sorted(
        (i for i in issues if i.kind == "respelled" and i.span and i.suggestion),
        key=lambda i: i.span[0],  # type: ignore[index]
        reverse=True,
    )
    fixed: str | None = None
    if fixes:
        fixed = banner_n
        for i in fixes:
            s, e = i.span  # type: ignore[misc]
            replacement = i.suggestion or ""
            if banner_n[s:e].isupper():
                replacement = replacement.upper()
            fixed = fixed[:s] + replacement + fixed[e:]
        if verify(note, names, fixed, approved).issues:
            fixed = None  # the repair itself must pass the same gate

    return Verdict(
        printable=not issues,
        names=names,
        issues=issues,
        fixed_banner=fixed,
    )
