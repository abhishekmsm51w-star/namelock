"""Twenty-name check.

    python bench.py --backend scripted              # faithful scripted drafter
    python bench.py --backend scripted-autocorrect  # SIMULATED tool that "fixes" names
    python bench.py --backend ollama                # your real local model

Counts:
  changed   the draft's banner lost the customer's exact spelling
  caught    changed, and the lock refused to print it
  leaked    changed, and the lock allowed printing   <-- must be 0
  blocked   the draft was faithful but the lock refused it (false alarm)

Exit code is 1 if anything leaked, so CI fails.
"""

from __future__ import annotations

import argparse
import sys
import time

from namelock.cases import notes
from namelock.drafter import DraftError, OllamaDrafter, ScriptedDrafter
from namelock.lock import _find, verify


def make(backend: str):
    if backend == "scripted":
        return ScriptedDrafter()
    if backend == "scripted-autocorrect":
        return ScriptedDrafter(autocorrect="banner")
    if backend == "ollama":
        d = OllamaDrafter()
        if not d.available():
            sys.exit(f"Model {d.model} is not ready at {d.host}. Run: ollama pull {d.model}")
        return d
    sys.exit(f"unknown backend {backend}")


def run(backend: str, verbose: bool) -> int:
    drafter = make(backend)
    rows = []
    for note, good, _bad in notes():
        t0 = time.perf_counter()
        try:
            d = drafter.draft(note)
        except DraftError as e:
            rows.append((good, "(error)", "error", str(e), 0.0))
            continue
        secs = time.perf_counter() - t0
        v = verify(note, d.names, d.banner)
        changed = _find(d.banner, good) is None or any(n != good for n in d.names)
        if changed and v.printable:
            outcome = "LEAKED"
        elif changed:
            outcome = "caught"
        elif not v.printable:
            outcome = "blocked"
        else:
            outcome = "ok"
        rows.append((good, d.banner, outcome, "; ".join(i.message for i in v.issues), secs))

    n = len(rows)
    count = lambda k: sum(1 for r in rows if r[2] == k)  # noqa: E731
    changed = count("caught") + count("LEAKED")
    print(f"\nbackend: {getattr(drafter, 'label', backend)}")
    print(f"names tested        : {n}")
    print(f"changed by drafter  : {changed}")
    print(f"  caught by lock    : {count('caught')}")
    print(f"  LEAKED to print   : {count('LEAKED')}")
    print(f"false alarms        : {count('blocked')}")
    print(f"errors              : {count('error')}")
    times = [r[4] for r in rows if r[4]]
    if times:
        print(f"draft time          : median {sorted(times)[len(times)//2]:.1f}s, max {max(times):.1f}s")
    if verbose or count("LEAKED") or count("blocked") or count("error"):
        print()
        for good, banner, outcome, why, _ in rows:
            if verbose or outcome in ("LEAKED", "blocked", "error"):
                print(f"[{outcome:7}] {good:12} -> {banner!r}  {why}")
    return 1 if count("LEAKED") else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default="scripted", choices=["scripted", "scripted-autocorrect", "ollama"])
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.backend, a.verbose))
