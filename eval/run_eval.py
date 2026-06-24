"""Eval harness for the SQL-agent interview.

Grades the candidate's agent (app.agent.answer_question) against a question set,
comparing RESULT SETS (not SQL text — many queries can be correct).

It supports two kinds of question file, auto-detected per question:

  * Answer-key mode  — question has "reference_sql". Ground truth is computed by
    running that query; on a failure the expected rows are shown. (interviewer kit)
  * Answer-hidden mode — question has "expected_hash" instead. The agent's result
    is hashed and compared to the stored hash; the target is never revealed.
    (candidate self-check)

Run it against whichever dataset is active (auto-selected from the seed file):

    uv run python -m eval.run_eval
    DB_FILE=shop_hard.db SEED_FILE=seed_hard.sql uv run python -m eval.run_eval
    uv run python -m eval.run_eval -v
    uv run python -m eval.run_eval --id B2

Comparison rules:
  * Numbers rounded to 2 decimals; ints and floats compare equal (15 == 15.0).
  * Strings stripped of surrounding whitespace.
  * Row ORDER ignored except for questions flagged "ordered" (top-N, time series).
  * Column ORDER is positional; column NAMES are ignored.

Exit codes: 0 = all passed, 1 = some failed/errored, 2 = agent not implemented.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from app import db
from app.agent import answer_question

DEFAULT_QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.json"
MAX_PREVIEW_ROWS = 8


# --- normalization, comparison, hashing -----------------------------------

def _norm_cell(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return None
    return str(value)


def _signature(rows, ordered: bool):
    """Canonical, comparable form of a result set (list of lists)."""
    normed = [[_norm_cell(c) for c in row] for row in rows]
    if not ordered:
        normed = sorted(normed, key=lambda r: tuple(repr(x) for x in r))
    return normed


def _matches(expected_rows, got_rows, ordered: bool) -> bool:
    return _signature(expected_rows, ordered) == _signature(got_rows, ordered)


def _sig_hash(rows, ordered: bool) -> str:
    canon = json.dumps(_signature(rows, ordered), separators=(",", ":"), default=str)
    return hashlib.sha256(canon.encode()).hexdigest()


def _preview(rows):
    shown = rows[:MAX_PREVIEW_ROWS]
    out = [str(r) for r in shown]
    if len(rows) > MAX_PREVIEW_ROWS:
        out.append(f"... (+{len(rows) - MAX_PREVIEW_ROWS} more rows)")
    return "\n        ".join(out) if out else "(no rows)"


# --- runner ----------------------------------------------------------------

def _active_dataset() -> str:
    """Infer which dataset is loaded from the seed file name."""
    return "hard" if "hard" in db.SEED_PATH.name.lower() else "base"


def run(questions_path: Path, selected_ids=None, verbose=False, dataset=None) -> int:
    data = json.loads(questions_path.read_text())
    questions = data["questions"]

    if selected_ids:
        wanted = {s.strip().upper() for s in selected_ids}
        questions = [q for q in questions if q["id"].upper() in wanted]
        if not questions:
            print(f"No questions matched {sorted(wanted)}")
            return 1
        chosen = dataset or "all"
    else:
        chosen = dataset or _active_dataset()
        if chosen != "all":
            questions = [q for q in questions if q.get("dataset", "base") == chosen]

    db.init_db()

    print(f"Dataset: {db.DB_PATH.name} (seed: {db.SEED_PATH.name})  |  grading: {chosen}")
    print(f"Running {len(questions)} question(s)\n")

    passed = failed = errored = skipped = 0

    for q in questions:
        qid, question, ordered = q["id"], q["question"], q.get("ordered", False)
        answer_key = "reference_sql" in q
        answer_hidden = "expected_hash" in q

        exp_rows = None
        if answer_key:
            # Ground truth. If the reference SQL doesn't fit the loaded dataset
            # (e.g. a hard question against the baseline DB), skip, don't crash.
            try:
                _, exp_rows = db.run_query(q["reference_sql"])
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                print(f"[SKIP] {qid} [{q['difficulty']}] — reference SQL doesn't apply to this dataset ({exc})")
                continue
        elif not answer_hidden:
            errored += 1
            print(f"[ERR ] {qid} — malformed question (needs reference_sql or expected_hash)")
            continue

        try:
            answer = answer_question(question)
        except NotImplementedError:
            print("Agent is not implemented yet.")
            print("Implement answer_question in app/agent.py, then re-run this eval.")
            return 2
        except Exception as exc:  # noqa: BLE001 — agent crashed on this question
            errored += 1
            print(f"[ERR ] {qid} [{q['difficulty']}] — {question}")
            print(f"        agent raised: {type(exc).__name__}: {exc}")
            continue

        if answer_key:
            ok = _matches(exp_rows, answer.rows, ordered)
        else:
            ok = _sig_hash(answer.rows, ordered) == q["expected_hash"]

        if ok:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"

        attempts = getattr(answer, "attempts", 1)
        suffix = f"  ({attempts} attempt{'s' if attempts != 1 else ''})" if attempts != 1 else ""
        print(f"[{status}] {qid} [{q['difficulty']}] — {question}{suffix}")

        if answer.error:
            print(f"        agent reported: {answer.error}")

        if verbose or not ok:
            print(f"        ordered: {ordered}")
            print(f"        your SQL: {answer.sql or '(none)'}")
            if answer_key:
                print(f"        expected: {_preview(exp_rows)}")
            print(f"        got:      {_preview(answer.rows)}")
            print()

    total = passed + failed + errored
    print("-" * 56)
    print(f"Passed {passed}/{total}   (failed {failed}, errored {errored}, skipped {skipped})")
    if total == 0 and skipped:
        print("Nothing graded — all questions were skipped. Check the active dataset / --dataset.")
        return 1
    return 0 if failed == 0 and errored == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Grade the SQL agent against the question set.")
    parser.add_argument("-v", "--verbose", action="store_true", help="show SQL + (in answer-key mode) expected vs got")
    parser.add_argument("--id", help="comma-separated question ids to run (e.g. Q3,Q9 or B2)")
    parser.add_argument("--dataset", choices=["base", "hard", "all"],
                        help="which question set to grade (default: inferred from the active seed file)")
    parser.add_argument("--questions", help="path to a questions JSON file (default: eval/questions.json)")
    parser.add_argument("--list", action="store_true", help="list questions and exit")
    args = parser.parse_args()

    questions_path = Path(args.questions) if args.questions else DEFAULT_QUESTIONS_PATH

    if args.list:
        data = json.loads(questions_path.read_text())
        for q in data["questions"]:
            tags = ",".join(q.get("tags", []))
            print(f"{q['id']:>3} [{q.get('dataset','base'):<4}] [{q['difficulty']:<6}] ({tags}) {q['question']}")
        sys.exit(0)

    selected = args.id.split(",") if args.id else None
    sys.exit(run(questions_path, selected_ids=selected, verbose=args.verbose, dataset=args.dataset))


if __name__ == "__main__":
    main()
