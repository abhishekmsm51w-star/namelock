"""Twenty names that chat tools like to 'fix', and the notes a shop actually receives.

Used by the tests and by bench.py. Replace these with the odd spellings from your
own shop's orders: the score is only as honest as the names you feed it.
"""

from __future__ import annotations

# (correct name, what an autocorrecting tool turns it into)
NAMES: list[tuple[str, str]] = [
    ("Aadhya", "Adya"),
    ("Khushboo", "Khushbu"),
    ("D'souza", "Dsouza"),
    ("Siobhan", "Shivon"),
    ("Mohammed", "Muhammad"),
    ("Siddharth", "Sidharth"),
    ("Shreya", "Shriya"),
    ("Jyothi", "Jyoti"),
    ("Lakshmi", "Laxmi"),
    ("Aaradhya", "Aradhya"),
    ("Zo\u00eb", "Zoe"),
    ("Jos\u00e9", "Jose"),
    ("Priyanka", "Priyanca"),
    ("Aaliyah", "Aliya"),
    ("Vaibhav", "Vaibav"),
    ("Thejaswini", "Tejaswini"),
    ("Keerthana", "Kirthana"),
    ("Anushka", "Anuska"),
    ("Mary-Anne", "Maryann"),
    ("Dhanush", "Dhanus"),
]

_TEMPLATES = [
    "blue flex 6 by 3, birthday, name {n}",
    "bhaiya birthday ka banner chahiye 6x3 red, naam {n} likhna",
    "wedding banner 8x4 pink, name {n}",
    "need a 4x2 green flex for engagement, name {n} please check spelling",
]


def notes() -> list[tuple[str, str, str]]:
    """(note, correct name, autocorrected spelling), one per name."""
    return [
        (_TEMPLATES[i % len(_TEMPLATES)].format(n=good), good, bad)
        for i, (good, bad) in enumerate(NAMES)
    ]
