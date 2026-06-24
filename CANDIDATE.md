# LLM SQL Agent — Take-Home / Pair Exercise

The web server, database, read-only query execution, and a minimal frontend are
already built. **Your job is to implement the agent** — turning a plain-English
question into SQL, running it, recovering from errors, and returning the result.
The LLM SDK and the agent loop are deliberately left out so you can use whatever
you like.

## Quickstart

```bash
uv sync                                   # install deps into a local venv
uv run uvicorn app.main:app --reload      # start the server
```

Open <http://127.0.0.1:8000>. The database is created and seeded automatically
on first run. See the schema your agent will receive:

```bash
curl http://127.0.0.1:8000/api/schema
```

## Your task

Open `app/agent.py` and implement `answer_question(question)`. Everything else
is wired up.

Add the LLM SDK of your choice (not installed by default):

```bash
uv add anthropic     # or:  uv add openai
```

…and set the API key environment variable your SDK expects before running.

The loop you're building, roughly:

1. Get the schema with `db.get_schema()` and include it in your prompt.
2. Ask the LLM for a SQL query.
3. Run it with `db.run_query(sql)`.
4. On error, feed the error back to the model and retry (with a sensible cap).
5. Return an `AgentAnswer(sql, columns, rows, attempts, error)`.

Then watch it work in the UI: type a question, see the generated SQL and the
result table.

## Layout

```
app/
  main.py            FastAPI app, routes, serves the frontend   (done)
  db.py              init/seed, read-only run_query, get_schema (done)
  agent.py           <-- YOU IMPLEMENT THIS
  static/index.html  minimal UI: question box, SQL view, table  (extend freely)
seed.sql             the dataset
eval/                a self-check you can run (see below)
pyproject.toml       uv project (web deps only)
```

## Helpers you get (`app/db.py`)

- `db.get_schema() -> str` — `CREATE TABLE` statements for your prompt.
- `db.run_query(sql) -> (columns, rows)` — executes a **read-only** SELECT.
  Raises `sqlite3.Error` on bad SQL (catch it and retry) and
  `db.UnsafeQueryError` if the query isn't a single SELECT. The connection is
  opened read-only, so the model cannot modify the database.

## Know your data

Spend a few minutes looking at what's actually in the tables, not just the
schema — understanding the real data is part of doing this well. You can hit
`/api/schema`, or open the DB directly:

```bash
uv run python -c "import sqlite3,glob;print(sqlite3.connect(glob.glob('*.db')[0]).execute('SELECT * FROM orders LIMIT 5').fetchall())"
```

Your interviewer may point the app at a larger dataset (`seed_hard.sql`); the
task is the same, just more data:

```bash
DB_FILE=shop_hard.db SEED_FILE=seed_hard.sql uv run uvicorn app.main:app --reload
```

## Self-check

There's a small test set you can run to check your agent. It reports pass/fail
per question; the expected answers are not shown — it just tells you whether
your result matches.

```bash
uv run python -m eval.run_eval          # checks against the loaded dataset
uv run python -m eval.run_eval -v       # also prints your SQL and your output
uv run python -m eval.run_eval --list   # list the questions
```

If you switch to the larger dataset, run the self-check with the same env vars
so it checks the matching questions:

```bash
DB_FILE=shop_hard.db SEED_FILE=seed_hard.sql uv run python -m eval.run_eval
```

A passing self-check is a good sign, but it isn't the whole evaluation — code
clarity, how you handle errors and edge cases, and how you use your tools all
matter too.

## Stretch goals

If you have time: auto-charting chartable results, an "explain this result in
plain English" follow-up, multi-step questions that need several queries, or
conversational follow-ups that build on the previous answer.
