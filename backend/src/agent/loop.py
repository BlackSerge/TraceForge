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
]

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


async def run_agent(
    issue_url: str,
    session: AsyncSession,
    *,
    issue_text: str | None = None,
    eval_run_id: uuid.UUID | None = None,
) -> AgentResult:
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING, eval_run_id=eval_run_id)
    session.add(run)
    await session.commit()

    client = get_llm_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": TASK_TEMPLATE.format(
                issue_url=issue_url,
                issue_text=issue_text or DEFAULT_ISSUE_TEXT,
                files="\n".join(f"- {f}" for f in tools.list_repo_files()),
            ),
        },
    ]
    suspicious = scan_issue(issue_text or DEFAULT_ISSUE_TEXT)
    test_runs = 0
    passed = False
    steps_taken = 0

    for step_id in range(1, MAX_STEPS + 1):
        steps_taken = step_id
        attempt = min(test_runs + 1, MAX_TEST_RUNS)
        context_snapshot = json.loads(json.dumps(messages))  # real context sent to the LLM
        step_tools = [t for t in TOOLS if t["function"]["name"] in READ_ONLY_TOOLS] if step_id == 1 else TOOLS
        started = time.perf_counter()
        try:
            reply = await client.chat(messages, step_tools)
        except Exception as exc:
            session.add(
                TraceStep(
                    run_id=run.id,
                    step_id=step_id,
                    input_context=_input_context(context_snapshot, step_tools, step_id, suspicious),
                    tool_calls=[],
                    reasoning_summary=f"LLM call failed: {type(exc).__name__}: {exc}",
                    outcome=StepOutcome.ERROR,
                    attempt=attempt,
                    latency_ms=int((time.perf_counter() - started) * 1000),
                )
            )
            run.status = RunStatus.FAILED
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return AgentResult(run.id, False, step_id, error=f"{type(exc).__name__}: {exc}")

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
            if call["name"] == "run_tests" and test_runs >= MAX_TEST_RUNS:
                result = {"error": "run_tests limit reached"}
            else:
                result = await _execute(call["name"], call["arguments"])
                if call["name"] == "run_tests" and "error" not in result:
                    test_runs += 1
                    step_tests_passed = step_tests_passed or bool(result.get("passed"))
            had_error = had_error or "error" in result
            record = {"name": call["name"], "args": call["arguments"], "result": result}
            if call["name"] == "run_tests" and tools.LAST_SANDBOX:
                record["sandbox"] = dict(tools.LAST_SANDBOX)
            recorded_calls.append(record)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"] or f"call_{step_id}_{i}",
                    "content": json.dumps(result),
                }
            )

        passed = step_tests_passed
        ran_failing_tests = any(
            c["name"] == "run_tests" and "error" not in c["result"] and not c["result"].get("passed")
            for c in recorded_calls
        )
        if not calls:
            outcome = StepOutcome.STOPPED  # model answered without using any tool
        elif had_error:
            outcome = StepOutcome.ERROR
        elif ran_failing_tests and test_runs < MAX_TEST_RUNS:
            outcome = StepOutcome.RETRY
        else:
            outcome = StepOutcome.SUCCESS

        session.add(
            TraceStep(
                run_id=run.id,
                step_id=step_id,
                input_context=_input_context(context_snapshot, step_tools, step_id, suspicious),
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

        if passed or not calls or test_runs >= MAX_TEST_RUNS:
            break

    run.status = RunStatus.AWAITING_APPROVAL if passed else RunStatus.FAILED
    run.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return AgentResult(run.id, passed, steps_taken)
