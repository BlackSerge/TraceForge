"""Orchestration: legacy single-role agent (evals) and the multi-role Triage -> Developer -> Reviewer flow."""
import difflib
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tools
from src.agent.cycle import MAX_TEST_RUNS, _run_cycle
from src.agent.llm.factory import get_llm_client
from src.agent.prompts import (
    DEFAULT_ISSUE_TEXT, DEVELOPER_PROMPT, REVIEWER_PROMPT, SYSTEM_PROMPT, TASK_TEMPLATE, TRIAGE_PROMPT,
)
from src.agent.tools import Workspace, default_workspace
from src.models.run import AgentRun, RunStatus

MAX_STEPS = 15

SUSPICIOUS_PATTERNS = [
    "ignore previous instructions", "ignore all previous", "rm -rf", "curl ", "wget ",
    "system(", "subprocess", "os.system", "eval(",
]


def scan_issue(issue_text: str) -> list[str]:
    """Audit only (never blocks): suspicious patterns found in the issue text."""
    lowered = issue_text.lower()
    return [p for p in SUSPICIOUS_PATTERNS if p in lowered]


@dataclass
class AgentResult:
    run_id: uuid.UUID
    passed: bool  # the agent's own view: its last run_tests passed
    steps: int
    error: str | None = None  # set when the LLM call failed (e.g. 429/503 after retries)



def _initial_message(ws: Workspace, issue_url: str, issue_text: str | None) -> str:
    return TASK_TEMPLATE.format(
        issue_url=issue_url,
        issue_text=issue_text or DEFAULT_ISSUE_TEXT,
        files="\n".join(f"- {f}" for f in tools.list_repo_files(ws)),
    )


async def _fail(session: AsyncSession, run: AgentRun, reason: str | None = None) -> None:
    run.status = RunStatus.FAILED
    run.rejection_reason = reason
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()


async def run_agent(
    issue_url: str,
    session: AsyncSession,
    *,
    issue_text: str | None = None,
    eval_run_id: uuid.UUID | None = None,
    workspace: Workspace | None = None,
) -> AgentResult:
    """Legacy single-role agent (role "coder"). Used by `make eval`."""
    ws = workspace or default_workspace()
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING, eval_run_id=eval_run_id)
    session.add(run)
    await session.commit()

    cycle = await _run_cycle(
        session, run, get_llm_client(), ws,
        role="coder", system_prompt=SYSTEM_PROMPT, user_content=_initial_message(ws, issue_url, issue_text),
        step_base=0, max_steps=MAX_STEPS, max_test_runs=MAX_TEST_RUNS, stop_on_pass=True,
        read_only_first_step=True, suspicious=scan_issue(issue_text or DEFAULT_ISSUE_TEXT),
    )
    if cycle.error:
        await _fail(session, run)
        return AgentResult(run.id, False, cycle.steps, error=cycle.error)
    if cycle.passed:
        run.status = RunStatus.AWAITING_APPROVAL
        run.finished_at = datetime.now(timezone.utc)
        await session.commit()
    else:
        await _fail(session, run)
    return AgentResult(run.id, cycle.passed, cycle.steps)


# ---------------------------------------------------------------- multi-role (hito 4)

TRIAGE_MAX_STEPS = 6
REVIEWER_MAX_STEPS = 8
REVIEWER_MAX_TEST_RUNS = 2

def _snapshot(ws: Workspace) -> dict[str, str]:
    root = ws.root.resolve()
    snap = {}
    for rel in tools.list_repo_files(ws):
        try:
            snap[rel] = (root / rel).read_text()
        except (UnicodeDecodeError, OSError):
            continue
    return snap


def _diff_snapshots(before: dict[str, str], after: dict[str, str]) -> str:
    chunks = []
    for rel in sorted(set(before) | set(after)):
        if before.get(rel) != after.get(rel):
            chunks.append(
                "".join(
                    difflib.unified_diff(
                        before.get(rel, "").splitlines(keepends=True),
                        after.get(rel, "").splitlines(keepends=True),
                        fromfile=f"a/{rel}",
                        tofile=f"b/{rel}",
                    )
                )
            )
    return "\n".join(chunks)


@dataclass
class MultiAgentResult:
    run_id: uuid.UUID
    status: RunStatus
    steps: int
    triage: dict | None = None  # {"verdict", "reason"}
    review: dict | None = None  # {"verdict", "reason"}
    error: str | None = None


async def run_multi_agent(
    issue_url: str,
    session: AsyncSession,
    *,
    issue_text: str | None = None,
    eval_run_id: uuid.UUID | None = None,
    workspace: Workspace | None = None,
) -> MultiAgentResult:
    """Sequential Triage -> Developer -> Reviewer. No Developer<->Reviewer loop: if the reviewer
    requests changes the run still waits for approval and the human decides.

    Final status: failed if triage says not_viable (reason in rejection_reason), if the developer
    does not make the tests pass, or on an LLM error; awaiting_approval otherwise. The reviewer's
    verdict lives in its TraceStep (submit_verdict tool call), no extra column.
    """
    ws = workspace or default_workspace()
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING, eval_run_id=eval_run_id)
    session.add(run)
    await session.commit()
    client = get_llm_client()
    text = issue_text or DEFAULT_ISSUE_TEXT
    task = _initial_message(ws, issue_url, issue_text)
    suspicious = scan_issue(text)
    steps = 0

    triage = await _run_cycle(
        session, run, client, ws, role="triage", system_prompt=TRIAGE_PROMPT, user_content=task,
        step_base=steps, max_steps=TRIAGE_MAX_STEPS, max_test_runs=0, stop_on_pass=False,
        read_only_first_step=False, suspicious=suspicious,
    )
    steps += triage.steps
    if triage.error:
        await _fail(session, run)
        return MultiAgentResult(run.id, run.status, steps, error=triage.error)
    if triage.decision is None:
        await _fail(session, run, "Triage: no verdict submitted")
        return MultiAgentResult(run.id, run.status, steps)
    if triage.decision["verdict"] != "viable":
        await _fail(session, run, f"Triage: not viable — {triage.decision['reason']}")
        return MultiAgentResult(run.id, run.status, steps, triage=triage.decision)

    before = _snapshot(ws)
    dev = await _run_cycle(
        session, run, client, ws, role="developer", system_prompt=DEVELOPER_PROMPT,
        user_content=f"{task}\nTriage assessment: {triage.decision['reason']}",
        step_base=steps, max_steps=MAX_STEPS, max_test_runs=MAX_TEST_RUNS, stop_on_pass=True,
        read_only_first_step=True, suspicious=[],
    )
    steps += dev.steps
    if dev.error:
        await _fail(session, run)
        return MultiAgentResult(run.id, run.status, steps, triage=triage.decision, error=dev.error)
    if not dev.passed:
        await _fail(session, run)
        return MultiAgentResult(run.id, run.status, steps, triage=triage.decision)

    diff = _diff_snapshots(before, _snapshot(ws))
    tests = dev.last_tests or {}
    review = await _run_cycle(
        session, run, client, ws, role="reviewer", system_prompt=REVIEWER_PROMPT,
        user_content=(
            f"{task}\n\nFinal diff by the developer:\n{diff or '(no changes)'}\n\n"
            f"Developer's last test result (passed={tests.get('passed')}):\n{tests.get('output', '')}"
        ),
        step_base=steps, max_steps=REVIEWER_MAX_STEPS, max_test_runs=REVIEWER_MAX_TEST_RUNS,
        stop_on_pass=False, read_only_first_step=False, suspicious=[],
    )
    steps += review.steps
    if review.error:
        await _fail(session, run)
        return MultiAgentResult(run.id, run.status, steps, triage=triage.decision, error=review.error)

    # No reviewer verdict (or changes_requested): still awaiting_approval, the human decides.
    run.status = RunStatus.AWAITING_APPROVAL
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return MultiAgentResult(run.id, run.status, steps, triage=triage.decision, review=review.decision)
