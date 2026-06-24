"""LangGraph agent that turns a plain-English question into SQL, runs it, and
recovers from errors by feeding them back to the LLM up to a retry cap.

Graph shape:

    START -> generate_sql -> run_sql -> (router) -> success -> visualize -> END
                  ^                         |
                  |__ retry (attempts < MAX)|__ attempts >= MAX -> give_up -> END
"""

from __future__ import annotations

import functools
import json
import os
import re
from dataclasses import dataclass
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from openai import OpenAI

from app import db
from dotenv import load_dotenv

load_dotenv()

# --- config ----------------------------------------------------------------

MODEL = os.environ.get("AGENT_MODEL", "gpt-4o")
MAX_ATTEMPTS = 4        # max SQL generation attempts before giving up

SMALL_TABLE_MAX = 12    # tables with <= this many rows are profiled in full
MAX_DISTINCT = 30       # cap on distinct values listed per categorical column
MAX_CHART_ROWS = 50     # max result rows to render as a chart

# Column-name hints that a label axis is a time series (line chart, not bar).
_TEMPORAL_HINTS = ("month", "date", "day", "year", "time", "period", "week", "quarter")

# Matches an ISO date or datetime string, e.g. '2024-06-01' or '2024-04-18T16:00:00-04:00'.
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2})?")

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Create the OpenAI client lazily so the module imports without a key set."""
    global _client
    if _client is None:
        # Retry transient errors (429/5xx/timeouts) with backoff.
        _client = OpenAI(max_retries=4)  # reads OPENAI_API_KEY from the environment
    return _client

SYSTEM_PROMPT = (
    "You are an expert data analyst who writes SQLite SQL.\n"
    "Given a database schema and a question, write ONE read-only SELECT "
    "query (a CTE with WITH is fine) that answers it.\n"
    "Rules:\n"
    "  - Output ONLY the SQL. No prose, no explanation, no markdown fences.\n"
    "  - A single statement only; never a semicolon-separated batch.\n"
    "  - Use only tables and columns that exist in the provided schema.\n"
    "  - If a previous attempt errored, read the error and fix the query.\n"
    " - Select ONLY the columns the question asks for: the human-readable "
    " label (e.g. name) plus the requested metric. Do NOT include surrogate"
    " id/primary-key columns or GROUP BY helper columns unless explicitly asked.\n"
    " - Order columns the way the question implies (label first, then the metric).\n"
    " - If the question asks for a single value (a count, total, average, etc.),"
    " return exactly that one value as a single column. Do NOT add a descriptive"
    " label/title literal column like 'Completed Orders'.\n"
    "A profile of the real data values is provided below the schema. Rely on it, "
    "not on assumptions:\n"
    "  - CASING: read the profile's 'Columns with INCONSISTENT casing/whitespace'"
    " list. A column there (and ONLY such a column) needs LOWER(TRIM(col)) when you"
    " filter or group on it, and you output the lowercased value. If that list is"
    " absent or a column is not on it, the column is CLEAN: filter/group/output it"
    " verbatim and never wrap it in LOWER/TRIM. (E.g. with no list, GROUP BY category"
    " and SELECT category, not LOWER(TRIM(category)).)\n"
    "  - When the question says 'in USD', convert non-USD amounts using the"
    " fx_rates table (multiply by rate_to_usd for the row's currency); USD is 1.0.\n"
    "  - Date/time columns are ISO 8601 strings with a timezone, NOT plain dates."
    " Use date(col) for a calendar DAY and strftime('%Y-%m', col) for a MONTH.\n"
    "  - Do NOT invent extra filters for vague terms. Use the simplest reasonable"
    " definition.\n"
    "  - Prefer the simplest query that works. To total a metric over detail rows"
    " (e.g. revenue per category), aggregate directly over the joined rows in one"
    " GROUP BY. Do NOT pre-aggregate per order in a CTE and then join the detail"
    " tables again; that double-counts.\n"
    "Domain conventions for this dataset, applied consistently:\n"
    "  - 'Revenue' / 'spend' / 'order value' = SUM(order_items.unit_price *"
    " order_items.quantity), converted to USD via the order's currency. It is NOT"
    " payments.amount.\n"
    "  - 'Amount paid' = SUM(payments.amount), converted to USD via the order's"
    " currency.\n"
    "  - 'Net' revenue subtracts refunds (refunds.amount, converted to USD via the"
    " order's currency); 'gross' revenue does NOT subtract refunds.\n"
    "  - Revenue/spend questions count orders whose status is 'completed' OR"
    " 'refunded' (case-insensitive) unless the question says otherwise.\n"
    "  - Group products by products.category directly (apply the CASING rule above);"
    " you usually do not need the product_categories lookup.\n"
    "  - An 'active'/'current' customer has deleted_at IS NULL. 'No subscription'"
    " means no row in subscriptions at all (any status)."

)


FOLLOWUP_PROMPT = (
    "You suggest follow-up analytics questions. Given the schema, the question "
    "just asked, and its result, propose 3 SHORT, natural follow-up questions a "
    "curious analyst would ask next. They must be answerable from the schema. "
    "Vary them (drill down, compare segments, change the time window or metric). "
    "Return ONLY a JSON array of 3 strings, nothing else."
)


@dataclass
class AgentAnswer:
    """Agent result, serialized into the API response."""
    sql: str                      # final SQL the agent settled on
    columns: list[str]            # result column names
    rows: list[list]              # result rows
    attempts: int = 1             # number of SQL attempts
    error: str | None = None      # error message if the agent gave up
    chart: dict | None = None     # {type, x_label, y_label, points} when chartable


class State(TypedDict):
    """State threaded through the graph."""
    question: str            # the user's plain-English question (input)
    schema: str              # CREATE TABLE statements for the prompt
    sql: str                 # latest SQL the LLM produced
    last_error: str | None   # error from the previous run, fed back to the LLM
    attempts: int            # how many times we've asked the LLM
    columns: list[str]       # result columns on success
    rows: list[list]         # result rows on success
    chart: dict | None       # chart spec for the UI, if the result is chartable
    error: str | None        # final error, set only when we give up


# --- nodes ------------------------------------------------------------------

def generate_sql(state: State) -> dict:
    """Ask the LLM for a SQL query.

    On a retry, the previous SQL and its error are included so the query can be
    corrected.
    """
    user_parts = [
        f"Question:\n{state['question']}",
        f"Database schema:\n{state['schema']}",
    ]
    if state.get("last_error"):
        user_parts.append(
            "Your previous query failed. Fix it.\n"
            f"Previous SQL:\n{state['sql']}\n\n"
            f"Error:\n{state['last_error']}"
        )

    attempts = state.get("attempts", 0) + 1
    try:
        response = _get_client().chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            temperature=0,
        )
    except Exception as exc:  # noqa: BLE001
        # LLM unreachable after retries: fail gracefully instead of raising.
        return {"attempts": attempts, "error": f"LLM request failed: {exc}"}

    sql = _strip_code_fence(response.choices[0].message.content or "")
    return {"sql": sql, "attempts": attempts}


def run_sql(state: State) -> dict:
    """Execute the latest SQL.

    On success, record columns/rows and clear any prior error. On failure, store
    the error for the router and the next generate_sql attempt.
    """
    try:
        columns, rows = db.run_query(state["sql"])
        return {"columns": columns, "rows": rows, "last_error": None, "error": None}
    except Exception as exc:  # noqa: BLE001  (sqlite3.Error / UnsafeQueryError: retry)
        return {"last_error": str(exc)}


# --- routing ----------------------------------------------------------------

def after_generate(state: State) -> str:
    """Conditional edge: run the SQL, unless the LLM call itself failed."""
    return "failed" if state.get("error") else "run"


def after_run(state: State) -> str:
    """Conditional edge: stop on success, retry while under the cap, else give up."""
    if not state.get("last_error"):
        return "done"
    if state["attempts"] < MAX_ATTEMPTS:
        return "retry"
    return "give_up"


def visualize(state: State) -> dict:
    """Attach a chart spec if the result is chartable (success path)."""
    return {"chart": suggest_chart(state["columns"], state["rows"])}


def give_up(state: State) -> dict:
    """Out of retries: promote last_error to the final error."""
    return {"error": state.get("last_error")}


def _is_numeric_column(rows: list[list], i: int) -> bool:
    vals = [r[i] for r in rows if r[i] is not None]
    return bool(vals) and all(
        isinstance(v, (int, float)) and not isinstance(v, bool) for v in vals
    )


def suggest_chart(columns: list[str], rows: list[list]) -> dict | None:
    """Heuristically turn a result set into a chart spec, or None if it isn't
    chartable.

    Chartable means: a manageable number of rows, a categorical/temporal label
    column, and a numeric value column. A line chart is used when the label
    looks like a time series, otherwise a bar chart. Returns a frontend-agnostic
    spec: {type, x_label, y_label, points: [[label, value], ...]}.
    """
    if not rows or len(columns) < 2 or len(rows) > MAX_CHART_ROWS:
        return None

    numeric = [i for i in range(len(columns)) if _is_numeric_column(rows, i)]
    if not numeric:
        return None

    # Label = first non-numeric column; fall back to the first column (e.g. a
    # year stored as an int) as long as a different numeric column remains.
    label_idx = next((i for i in range(len(columns)) if i not in numeric), 0)
    value_idx = next((i for i in numeric if i != label_idx), None)
    if value_idx is None:
        return None

    labels = [("" if r[label_idx] is None else str(r[label_idx])) for r in rows]
    name = columns[label_idx].lower()
    temporal = any(h in name for h in _TEMPORAL_HINTS) or all(
        _TIMESTAMP_RE.match(lbl) for lbl in labels if lbl
    )
    return {
        "type": "line" if temporal else "bar",
        "x_label": columns[label_idx],
        "y_label": columns[value_idx],
        "points": [[lbl, float(r[value_idx])] for lbl, r in zip(labels, rows)],
    }


# --- graph ------------------------------------------------------------------

def _build_graph():
    graph = StateGraph(State)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("run_sql", run_sql)
    graph.add_node("visualize", visualize)
    graph.add_node("give_up", give_up)

    graph.add_edge(START, "generate_sql")
    graph.add_conditional_edges(
        "generate_sql",
        after_generate,
        {"run": "run_sql", "failed": END},
    )
    graph.add_conditional_edges(
        "run_sql",
        after_run,
        {"done": "visualize", "retry": "generate_sql", "give_up": "give_up"},
    )
    graph.add_edge("visualize", END)
    graph.add_edge("give_up", END)
    return graph.compile()


AGENT = _build_graph()


# --- helpers ----------------------------------------------------------------

def _strip_code_fence(text: str) -> str:
    """Models sometimes wrap SQL in ```sql ... ``` fences; strip them if present."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


def _looks_like_timestamp(value: str) -> bool:
    return bool(_TIMESTAMP_RE.match(value))


@functools.lru_cache(maxsize=2)
def build_db_context() -> str:
    """Schema plus a lightweight data profile.

    The CREATE TABLE schema alone omits details that affect query correctness:
    inconsistent casing in status/category values, which currencies exist, and
    that timestamps are ISO strings rather than plain dates. The profile adds:
      - small lookup tables (fx_rates, plans, countries, ...) dumped in full,
      - distinct values of categorical text columns in larger tables,
      - a format note for timestamp columns.

    Read-only (built from SELECTs via db.run_query) and cached, since the data
    does not change within a process.
    """
    sections = [db.get_schema()]
    profile: list[str] = []
    messy: list[str] = []  # columns whose distinct values collide under LOWER(TRIM)

    _, trows = db.run_query(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    )
    for table in [r[0] for r in trows]:
        try:
            cols, sample = db.run_query(f'SELECT * FROM "{table}" LIMIT 50')
        except Exception:  # noqa: BLE001  (skip tables we can't introspect)
            continue
        if not cols:
            continue
        _, crows = db.run_query(f'SELECT COUNT(*) FROM "{table}"')
        count = crows[0][0]

        # Scan text columns for distinct values and detect case/whitespace
        # variants, so the prompt can name which columns need LOWER(TRIM).
        lines = []
        for i, col in enumerate(cols):
            if col.lower() == "id" or col.lower().endswith("_id"):
                continue
            vals = [r[i] for r in sample if r[i] is not None]
            if not vals or not all(isinstance(v, str) for v in vals):
                continue
            if any(_looks_like_timestamp(v) for v in vals):
                if count > SMALL_TABLE_MAX:
                    lines.append(
                        f"      {col}: timestamp string e.g. {vals[0]!r} "
                        f"(use date({col}) to compare by day)"
                    )
                continue
            _, drows = db.run_query(
                f'SELECT DISTINCT "{col}" FROM "{table}" LIMIT {MAX_DISTINCT + 1}'
            )
            distinct = [r[0] for r in drows if r[0] is not None]
            if not (1 <= len(distinct) <= MAX_DISTINCT):
                continue
            if len({v.strip().lower() for v in distinct}) < len(distinct):
                messy.append(
                    f"  {table}.{col}: " + ", ".join(repr(v) for v in distinct)
                )
            if count > SMALL_TABLE_MAX:
                lines.append(
                    f"      {col} distinct: " + ", ".join(repr(v) for v in distinct)
                )

        if count <= SMALL_TABLE_MAX:
            _, all_rows = db.run_query(f'SELECT * FROM "{table}"')
            rendered = "\n".join(
                "      " + " | ".join(repr(c) for c in row) for row in all_rows
            )
            profile.append(
                f"  {table} (all {count} rows) [{', '.join(cols)}]:\n{rendered}"
            )
        elif lines:
            profile.append(f"  {table} ({count} rows):\n" + "\n".join(lines))

    if profile:
        sections.append(
            "Data profile (note which currencies exist and how timestamps are "
            "formatted):\n" + "\n".join(profile)
        )
    if messy:
        sections.append(
            "Columns with INCONSISTENT casing/whitespace (different spellings of the "
            "same value). For THESE columns only, use LOWER(TRIM(col)) when filtering "
            "or grouping, and output the lowercased value when grouping. Every other "
            "text column is clean; use it exactly as stored:\n" + "\n".join(messy)
        )
    return "\n\n".join(sections)


def answer_question(question: str) -> AgentAnswer:
    """Entry point called by the web server: NL question -> AgentAnswer."""
    final = AGENT.invoke(_initial_state(question))
    return AgentAnswer(
        sql=final.get("sql", ""),
        columns=final.get("columns", []),
        rows=final.get("rows", []),
        attempts=final.get("attempts", 1),
        error=final.get("error"),
        chart=final.get("chart"),
    )


def _initial_state(question: str) -> dict:
    return {
        "question": question,
        "schema": build_db_context(),
        "sql": "",
        "last_error": None,
        "attempts": 0,
        "columns": [],
        "rows": [],
        "chart": None,
        "error": None,
    }


def _parse_questions(text: str) -> list[str]:
    """Pull up to 3 question strings out of the model's reply (JSON or a list)."""
    text = _strip_code_fence(text)
    items: list[str] = []
    try:
        data = json.loads(text)
        if isinstance(data, list):
            items = [str(x) for x in data]
    except Exception:  # noqa: BLE001  (fall back to line parsing)
        for line in text.splitlines():
            items.append(line.strip().lstrip("-*0123456789. ").strip().strip('"'))
    return [q.strip() for q in items if q.strip()][:3]


def suggest_followups(question: str, columns: list[str], rows: list[list]) -> list[str]:
    """Ask the LLM for 3 follow-up questions grounded in the schema + result.

    Best-effort and UI-only: any failure returns [] so the answer is never
    affected.
    """
    preview = {"columns": columns, "rows": rows[:5]}
    user = (
        f"Schema:\n{build_db_context()}\n\n"
        f"Question asked:\n{question}\n\n"
        f"Result preview (up to 5 rows):\n{json.dumps(preview, default=str)}"
    )
    response = _get_client().chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": FOLLOWUP_PROMPT},
            {"role": "user", "content": user},
        ],
        temperature=0.4,
    )
    return _parse_questions(response.choices[0].message.content or "")
