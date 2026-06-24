"""FastAPI app wiring the frontend to the agent.

Run with:
    uv run uvicorn app.main:app --reload
then open http://127.0.0.1:8000
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import db
from app.agent import answer_question, suggest_followups

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="LLM SQL Agent")


@app.on_event("startup")
def _startup() -> None:
    db.init_db()  # seeds shop.db on first run


class QueryRequest(BaseModel):
    question: str


class SuggestRequest(BaseModel):
    question: str
    columns: list[str] = []
    rows: list[list] = []


@app.get("/api/schema")
def schema() -> dict:
    """Return the database schema (useful for inspecting the DB)."""
    return {"schema": db.get_schema()}


@app.post("/api/query")
def query(req: QueryRequest) -> dict:
    question = (req.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question must not be empty.")
    try:
        answer = answer_question(question)
    except NotImplementedError as exc:
        # Agent not implemented: report clearly instead of a 500.
        raise HTTPException(status_code=501, detail=str(exc))
    except Exception as exc:  # noqa: BLE001  (report agent crashes to the UI)
        raise HTTPException(status_code=500, detail=f"Agent error: {exc}")
    return {
        "sql": answer.sql,
        "columns": answer.columns,
        "rows": answer.rows,
        "attempts": answer.attempts,
        "error": answer.error,
        "chart": answer.chart,
    }


@app.post("/api/suggest")
def suggest(req: SuggestRequest) -> dict:
    """Follow-up question suggestions for a result. Best-effort: returns an empty
    list rather than erroring, so a failure never disrupts the main answer."""
    question = (req.question or "").strip()
    if not question or not req.rows:
        return {"suggestions": []}
    try:
        return {"suggestions": suggest_followups(question, req.columns, req.rows)}
    except Exception:  # noqa: BLE001  (suggestions are optional)
        return {"suggestions": []}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# Serve static assets.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
