"""Recorded demo runs, so the inbox is not empty without an LLM key.

  python scripts/demo_data.py export <run_id> [<run_id> ...]   write demo/runs.json from the database
  python scripts/demo_data.py seed                             load demo/runs.json (idempotent)

The runs are real multi-role traces recorded with Gemini Flash Lite. On seed they are set to
awaiting_approval so the approve/reject flow can be tried; the recorded steps are untouched.
"""
import asyncio
import json
import sys
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from src.db.session import SessionLocal, engine  # noqa: E402
from src.models.run import AgentRun, RunStatus  # noqa: E402
from src.models.trace import TraceStep  # noqa: E402

DEMO_FILE = Path(__file__).resolve().parents[1] / "demo" / "runs.json"
SKIP_COLUMNS = {"eval_run_id"}  # demo runs do not belong to an eval run


def _dump(obj) -> dict:
    out = {}
    for col in inspect(type(obj)).columns:
        if col.key in SKIP_COLUMNS:
            continue
        value = getattr(obj, col.key)
        if isinstance(value, (uuid.UUID, datetime)):
            value = str(value) if isinstance(value, uuid.UUID) else value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)
        elif hasattr(value, "value"):  # enums
            value = value.value
        out[col.key] = value
    return out


def _strip_extra_content(messages: list) -> None:
    """Gemini's opaque thought_signature blobs add size and no information."""
    for m in messages:
        for call in m.get("tool_calls") or []:
            call.pop("extra_content", None)


def _issue_from_context(steps: list[dict]) -> str | None:
    """Runs recorded before agent_run.issue_text existed: recover it from the first prompt."""
    for s in steps:
        for m in s["input_context"].get("messages", []):
            if m.get("role") == "user" and "Description: " in (m.get("content") or ""):
                return m["content"].split("Description: ", 1)[1].split("\nRepository files:", 1)[0]
    return None


def _load(model, data: dict):
    values = {}
    for col in inspect(model).columns:
        if col.key not in data:
            continue
        value, py = data[col.key], col.type.python_type
        if value is not None:
            if py is uuid.UUID:
                value = uuid.UUID(value)
            elif py is datetime:
                value = datetime.fromisoformat(value)
            elif py is Decimal:
                value = Decimal(value)
        values[col.key] = value
    return model(**values)


async def export(run_ids: list[str]) -> None:
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(AgentRun)
                .where(AgentRun.id.in_([uuid.UUID(r) for r in run_ids]))
                .options(selectinload(AgentRun.steps))
                .order_by(AgentRun.created_at)
            )
        ).scalars().all()
        DEMO_FILE.parent.mkdir(exist_ok=True)
        out = []
        for r in rows:
            data = {**_dump(r), "steps": [_dump(s) for s in r.steps]}
            for step in data["steps"]:
                _strip_extra_content(step["input_context"].get("messages", []))
            data["issue_text"] = data["issue_text"] or _issue_from_context(data["steps"])
            out.append(data)
        DEMO_FILE.write_text(json.dumps(out, indent=1) + "\n")
    print(f"exported {len(rows)} runs to {DEMO_FILE}")


async def seed() -> None:
    runs = json.loads(DEMO_FILE.read_text())
    added = 0
    async with SessionLocal() as session:
        for data in runs:
            run_id = uuid.UUID(data["id"])
            if await session.get(AgentRun, run_id) is not None:
                continue
            run = _load(AgentRun, {k: v for k, v in data.items() if k != "steps"})
            run.status = RunStatus.AWAITING_APPROVAL
            run.rejection_reason = None
            session.add(run)
            await session.flush()
            session.add_all(_load(TraceStep, s) for s in data["steps"])
            added += 1
        await session.commit()
    print(f"seeded {added} new runs ({len(runs) - added} already present)")


async def main() -> None:
    cmd, *args = sys.argv[1:] or ["seed"]
    if cmd == "export" and args:
        await export(args)
    elif cmd == "seed":
        await seed()
    else:
        print(__doc__)
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
