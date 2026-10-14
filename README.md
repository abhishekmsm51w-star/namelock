# NameLock

A flex-banner and wedding-card print shop gets a customer's name by WhatsApp. A local open-weight
model (Gemma, through Ollama) drafts the banner. **The model may not change a single letter of a
name.** A plain-Python check compares every name to the customer's own words, and the print
button stays off until they match.

Built for the Hacktoberfest Open-Source AI Challenge, Week 2 (Side Hustle).

## Why open matters here

- Customer names and phone numbers stay on the shop's laptop. The model runs locally.
- No fee per banner.
- A hosted chat tool tends to "fix" a spelling. For this shop that is the mistake that causes a reprint.
  With your own model you can pin the instructions and swap the model; the lock does not care which.

## How it works

1. `drafter.py` - Gemma via Ollama reads the message and returns names, size, colour and banner text as JSON.
2. `lock.py` - `verify()` checks each name against the customer's message and the banner. No model involved.
   Blocks: a spelling the customer rejected ("not Adya"), a name not in their message, a name missing
   from the banner, a near-miss respelling on the banner. Asks for confirmation: a spelling close to
   one the shop already approved.
3. `app.py` - the server re-checks before it will return a print page, so bypassing the browser does not help.
4. `book.py` - approved spellings, in SQLite by default or any Postgres (Tiger Cloud) via `DATABASE_URL`.

## Run it

```bash
pip install -r requirements.txt
ollama pull gemma3:4b            # model name is set by NAMELOCK_MODEL
uvicorn namelock.app:app --port 8000
```

Public demo mode (no model, sample notes, in-memory book): `NAMELOCK_BACKEND=demo`.
`render.yaml` deploys that mode on Render.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python bench.py --backend scripted-autocorrect   # SIMULATED tool that "fixes" 20 names
python bench.py --backend ollama                 # the real model, once Ollama is running
```

`bench.py` exits non-zero if any changed name could still print. GitHub Actions runs it on every push.

## Status (as of 2026-10-15)

Done and verified:
- Lock, spelling book (SQLite), scripted drafter, web page, print gate. 105 tests pass.
  Breaking the lock on purpose makes 26 of them fail, so they are not vacuous.
- Scripted benchmark: 20 of 20 autocorrected names caught, 0 leaked. This is a simulation of a
  tool that rewrites names, not a measurement of Gemma.

Not done:
- Ollama is not confirmed installed on this machine. The winget download had not finished after
  12 minutes and may still be running, so check `ollama --version` first. Until it works, there is no
  real Gemma number. If it is missing, run `winget install Ollama.Ollama`, then `ollama pull gemma3:4b`, then
  `python bench.py --backend ollama -v`. Check that tag exists or set `NAMELOCK_MODEL`.
- Tiger: `PostgresBook` is written but never run. The saved password for service `db-18894`
  was rejected (`password authentication failed for user "tsdbadmin"`). Get a working connection
  string, set `DATABASE_URL`, `pip install -r requirements-tiger.txt`, and try it.
  It stores approved names only; it does not use pgvector or hybrid search.
- Not yet looked at in a browser (screenshot attempt was interrupted).
- Render deploy, `.tech` domain, a real shop's twenty odd names in `namelock/cases.py`, a first user,
  and the DEV post.

Challenge closes 2026-10-18 11:59 PM PDT (12:29 PM IST on 2026-10-19). Tags: `#devchallenge` `#hf26challenge`.

## License

MIT
