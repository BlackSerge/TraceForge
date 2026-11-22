import difflib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tools
from src.agent.llm.factory import get_llm_client
from src.models.run import AgentRun, RunStatus
from src.models.trace import StepOutcome, TraceStep

SUSPICIOUS_PATTERNS = [
    "ignore previous instructions", "ignore all previous", "rm -rf", "curl ", "wget ",
    "system(", "subprocess", "os.system", "eval(",
]


def scan_issue(issue_text: str) -> list[str]:
    """Audit only (never blocks): suspicious patterns found in the issue text."""
    lowered = issue_text.lower()
    return [p for p in SUSPICIOUS_PATTERNS if p in lowered]


MAX_STEPS = 15
MAX_TEST_RUNS = 3
READ_ONLY_TOOLS = {"read_file", "list_files"}  # the only tools offered in step 1

SYSTEM_PROMPT = (
    "You are a coding agent. Your goal is to make the repository's tests pass. "
    "Tools: list_files lists a directory of the repository to explore it (use it when you do not "
    "know which file is relevant); read_file inspects a file; propose_patch REALLY modifies the file on disk with the "
    "full new content you give it; run_tests runs the real test suite and reports its output. "
    "In the first step you can only read and list (read_file, list_files): you cannot propose "
    "patches or run tests yet; from the second step on you can also use propose_patch and "
    "run_tests. Workflow: explore with list_files if needed, read the relevant files, propose a patch with propose_patch, then "
    "run the tests with run_tests. If the tests fail, read the test output, correct your patch "
    "and run the tests again. Every tool call requires a brief 'reasoning' argument justifying it. "
    "Stop calling tools once the tests pass."
)

# Issue fetching is not implemented yet: the issue text is passed in (or defaulted).
DEFAULT_ISSUE_TEXT = "the function add(a, b) in sample.py returns the wrong result. Fix it."
TASK_TEMPLATE = "Issue: {issue_url}\nDescription: {issue_text}\nRepository files:\n{files}"


def _input_context(messages: list, step_tools: list, step_id: int, suspicious: list[str]) -> dict:
    ctx = {"messages": messages, "tools": [t["function"]["name"] for t in step_tools]}
    if step_id == 1 and suspicious:
        ctx["suspicious_issue"] = True
        ctx["suspicious_patterns"] = suspicious
    return ctx


@dataclass
class AgentResult:
    run_id: uuid.UUID
    passed: bool  # the agent's own view: its last run_tests passed
    steps: int
    error: str | None = None  # set when the LLM call failed (e.g. 429/503 after retries)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List the entries (files and directories) of a directory in the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory relative to the repo root. Defaults to '.'.",
                        "default": ".",
                    },
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the repository.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path relative to the repo root."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["path", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_patch",
            "description": "Propose the full new content of a file; returns a unified diff.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file": {"type": "string", "description": "Path relative to the repo root."},
                    "new_content": {"type": "string", "description": "Full new content of the file."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["file", "new_content", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run the test suite and return whether it passed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_triage",
            "description": "Final decision of the triage: is the issue viable for an automated fix?",
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["viable", "not_viable"]},
                    "reason": {"type": "string", "description": "Why the issue is or is not viable."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["verdict", "reason", "reasoning"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verdict",
            "description": "Final review verdict on the developer's patch.",
            "parameters": {
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["approved", "changes_requested"]},
                    "reason": {"type": "string", "description": "Why the patch is approved or needs changes."},
                    "reasoning": {"type": "string", "description": "Brief justification for this tool call"},
                },
                "required": ["verdict", "reason", "reasoning"],
            },
        },
    },
]

TOOLS_BY_NAME = {t["function"]["name"]: t for t in TOOLS}

# Role permissions = which tools each role is OFFERED (and allowed to execute) in its cycle.
# Not enforced at DB level (future work). "coder" is the legacy single-role agent used by evals.
DECISION_TOOLS = {"submit_triage": {"viable", "not_viable"}, "submit_verdict": {"approved", "changes_requested"}}
ROLE_TOOLS = {
    "coder": ["list_files", "read_file", "propose_patch", "run_tests"],
    "developer": ["list_files", "read_file", "propose_patch", "run_tests"],
    "triage": ["list_files", "read_file", "submit_triage"],
    "reviewer": ["list_files", "read_file", "run_tests", "submit_verdict"],  # no propose_patch
}

TOOL_FUNCS = {
    "list_files": tools.list_files,
    "read_file": tools.read_file,
    "propose_patch": tools.propose_patch,
    "run_tests": tools.run_tests,
}


async def _execute(name: str, args: dict) -> dict:
    func = TOOL_FUNCS.get(name)
    if func is None:
        return {"error": f"unknown tool: {name}"}
    args = {k: v for k, v in args.items() if k != "reasoning"}
    try:
        return await func(**args)
    except Exception as exc:  # tool failures are data for the model, not crashes
        return {"error": f"{type(exc).__name__}: {exc}"}


@dataclass
class CycleResult:
    steps: int  # steps taken in this cycle
    passed: bool  # last run_tests of the cycle passed
    last_tests: dict | None  # last successful run_tests result of the cycle
    decision: dict | None  # {"verdict", "reason"} from submit_triage / submit_verdict
    error: str | None = None  # LLM failure


async def _run_cycle(
    session: AsyncSession,
    run: AgentRun,
    client,
    *,
    role: str,
    system_prompt: str,
    user_content: str,
    step_base: int,
    max_steps: int,
    max_test_runs: int,
    stop_on_pass: bool,
    read_only_first_step: bool,
    suspicious: list[str],
) -> CycleResult:
    """One role's LLM cycle. step_id is global to the run: step_base + local step number."""
    allowed = ROLE_TOOLS[role]
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    test_runs = 0
    passed = False
    last_tests: dict | None = None
    decision: dict | None = None
    steps_taken = 0

    for local in range(1, max_steps + 1):
        steps_taken = local
        step_id = step_base + local
        attempt = min(test_runs + 1, MAX_TEST_RUNS)
        context_snapshot = json.loads(json.dumps(messages))  # real context sent to the LLM
        offered = [n for n in allowed if n in READ_ONLY_TOOLS] if (read_only_first_step and local == 1) else allowed
        step_tools = [TOOLS_BY_NAME[n] for n in offered]
        ctx = _input_context(context_snapshot, step_tools, step_id, suspicious)
        started = time.perf_counter()
        try:
            reply = await client.chat(messages, step_tools)
        except Exception as exc:
            session.add(
                TraceStep(
                    run_id=run.id,
                    step_id=step_id,
                    agent_role=role,
                    input_context=ctx,
                    tool_calls=[],
                    reasoning_summary=f"LLM call failed: {type(exc).__name__}: {exc}",
                    outcome=StepOutcome.ERROR,
                    attempt=attempt,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            await session.commit()
            return CycleResult(local, False, last_tests, decision, error=f"{type(exc).__name__}: {exc}")

        calls = reply["tool_calls"]
        messages.append(
            {
                "role": "assistant",
                "content": reply["content"],
                **(
                    {
                        "tool_calls": [
                            {
                                "id": c["id"] or f"call_{step_id}_{i}",
                                "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                                **({"extra_content": c["extra_content"]} if c.get("extra_content") else {}),
                            }
                            for i, c in enumerate(calls)
                        ]
                    }
                    if calls
                    else {}
                ),
            }
        )

        recorded_calls = []
        had_error = False
        step_tests_passed = False
        for i, call in enumerate(calls):
            name, args = call["name"], call["arguments"]
            if name not in offered:  # enforced at execution, not just by the offered schema
                result = {"error": f"tool '{name}' is not available to role '{role}' at this step"}
            elif name in DECISION_TOOLS:
                if args.get("verdict") in DECISION_TOOLS[name]:
                    decision = {"verdict": args["verdict"], "reason": args.get("reason") or ""}
                    result = {"recorded": True}
                else:
                    result = {"error": f"verdict must be one of {sorted(DECISION_TOOLS[name])}"}
            elif name == "run_tests" and test_runs >= max_test_runs:
                result = {"error": "run_tests limit reached"}
            else:
                result = await _execute(name, args)
                if name == "run_tests" and "error" not in result:
                    test_runs += 1
                    last_tests = result
                    step_tests_passed = step_tests_passed or bool(result.get("passed"))
            had_error = had_error or "error" in result
            record = {"name": name, "args": args, "result": result}
            if name == "run_tests" and tools.LAST_SANDBOX and "error" not in result:
                record["sandbox"] = dict(tools.LAST_SANDBOX)
            recorded_calls.append(record)
            messages.append(
                {"role": "tool", "tool_call_id": call["id"] or f"call_{step_id}_{i}", "content": json.dumps(result)}
            )

        if any(c["name"] == "run_tests" for c in calls):
            passed = step_tests_passed
        ran_failing_tests = any(
            c["name"] == "run_tests" and "error" not in c["result"] and not c["result"].get("passed")
            for c in recorded_calls
        )
        if not calls:
            outcome = StepOutcome.STOPPED  # model answered without using any tool
        elif had_error:
            outcome = StepOutcome.ERROR
        elif ran_failing_tests and test_runs < max_test_runs:
            outcome = StepOutcome.RETRY
        else:
            outcome = StepOutcome.SUCCESS

        session.add(
            TraceStep(
                run_id=run.id,
                step_id=step_id,
                agent_role=role,
                input_context=ctx,
                tool_calls=recorded_calls,
                reasoning_summary=(calls[0]["arguments"].get("reasoning") or "") if calls else (reply["content"] or ""),
                outcome=outcome,
                attempt=attempt,
                latency_ms=int((time.perf_counter() - started) * 1000),
                tokens_in=reply["tokens_in"],
                tokens_out=reply["tokens_out"],
                cost_usd=None,
                model=reply["model"],
            )
        )
        await session.commit()

        if decision is not None or not calls:
            break
        if stop_on_pass and (passed or test_runs >= max_test_runs):
            break

    return CycleResult(steps_taken, passed, last_tests, decision)


def _initial_message(issue_url: str, issue_text: str | None) -> str:
    return TASK_TEMPLATE.format(
        issue_url=issue_url,
        issue_text=issue_text or DEFAULT_ISSUE_TEXT,
        files="\n".join(f"- {f}" for f in tools.list_repo_files()),
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
) -> AgentResult:
    """Legacy single-role agent (role "coder"). Used by `make eval`."""
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING, eval_run_id=eval_run_id)
    session.add(run)
    await session.commit()

    cycle = await _run_cycle(
        session, run, get_llm_client(),
        role="coder", system_prompt=SYSTEM_PROMPT, user_content=_initial_message(issue_url, issue_text),
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

TRIAGE_PROMPT = (
    "You are the TRIAGE role of a coding-agent team. Decide whether the issue can be fixed "
    "automatically in this repository. Tools: list_files and read_file to explore; submit_triage "
    "to give your final decision. You cannot modify code or run tests. Explore only as much as "
    "needed, then call submit_triage with verdict 'viable' (a concrete, fixable code bug is "
    "identifiable) or 'not_viable' (the issue is vague, not a code bug, or not fixable from this "
    "repository) and a clear reason. Every tool call requires a brief 'reasoning' argument."
)

DEVELOPER_PROMPT = (
    "You are the DEVELOPER role of a coding-agent team. Your goal is to make the repository's "
    "tests pass. Tools: list_files lists a directory; read_file inspects a file; propose_patch "
    "REALLY modifies the file on disk with the full new content you give it; run_tests runs the "
    "real test suite. In your first step you can only read and list; from the second step on you "
    "can also propose patches and run tests. Workflow: explore, read the relevant files, propose a "
    "patch, run the tests; if they fail, read the output, correct the patch and run again. Every "
    "tool call requires a brief 'reasoning' argument. Stop calling tools once the tests pass."
)

# LIMITATION: with a small model (Gemini Flash Lite) the reviewer is permissive and tends to
# approve almost every patch that makes the tests pass. The prompt asks for scrutiny but the
# verdict is not forced: a reviewer that never rejects is a measured limitation, not a bug.
REVIEWER_PROMPT = (
    "You are the REVIEWER role of a coding-agent team. A developer already patched the repository. "
    "You receive the issue, the final diff and the developer's last test result. Review critically: "
    "does the diff really fix the issue described, without unrelated changes, hacks (hard-coded "
    "values, special-casing the tests) or regressions? Tools: list_files and read_file to inspect, "
    "run_tests to re-run the suite, submit_verdict to give your final decision. You CANNOT modify "
    "code. Call submit_verdict with 'approved' or 'changes_requested' and a clear reason. Every "
    "tool call requires a brief 'reasoning' argument."
)


def _snapshot() -> dict[str, str]:
    root = tools.FIXTURE_REPO.resolve()
    snap = {}
    for rel in tools.list_repo_files():
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
) -> MultiAgentResult:
    """Sequential Triage -> Developer -> Reviewer. No Developer<->Reviewer loop: if the reviewer
    requests changes the run still waits for approval and the human decides.

    Final status: failed if triage says not_viable (reason in rejection_reason), if the developer
    does not make the tests pass, or on an LLM error; awaiting_approval otherwise. The reviewer's
    verdict lives in its TraceStep (submit_verdict tool call), no extra column.
    """
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING, eval_run_id=eval_run_id)
    session.add(run)
    await session.commit()
    client = get_llm_client()
    text = issue_text or DEFAULT_ISSUE_TEXT
    task = _initial_message(issue_url, issue_text)
    suspicious = scan_issue(text)
    steps = 0

    triage = await _run_cycle(
        session, run, client, role="triage", system_prompt=TRIAGE_PROMPT, user_content=task,
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

    before = _snapshot()
    dev = await _run_cycle(
        session, run, client, role="developer", system_prompt=DEVELOPER_PROMPT,
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

    diff = _diff_snapshots(before, _snapshot())
    tests = dev.last_tests or {}
    review = await _run_cycle(
        session, run, client, role="reviewer", system_prompt=REVIEWER_PROMPT,
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
