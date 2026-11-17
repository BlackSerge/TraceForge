import json
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tools
from src.agent.llm.factory import get_llm_client
from src.models.run import AgentRun, RunStatus
from src.models.trace import StepOutcome, TraceStep

MAX_STEPS = 15
MAX_TEST_RUNS = 3

SYSTEM_PROMPT = (
    "You are a coding agent. Your goal is to make the repository's tests pass. "
    "Tools: read_file inspects a file; propose_patch REALLY modifies the file on disk with the "
    "full new content you give it; run_tests runs the real test suite and reports its output. "
    "In the first step you can only read (read_file); after that you can also propose patches "
    "and run tests. Workflow: read the relevant files, propose a patch with propose_patch, then "
    "run the tests with run_tests. If the tests fail, read the test output, correct your patch "
    "and run the tests again. Every tool call requires a brief 'reasoning' argument justifying it. "
    "Stop calling tools once the tests pass."
)

# Issue fetching is not implemented yet: the task text is fixed for the fixture repo.
TASK_TEMPLATE = (
    "Issue: {issue_url}\n"
    "Description: the function add(a, b) in sample.py returns the wrong result. Fix it."
)

TOOLS = [
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


async def run_agent(issue_url: str, session: AsyncSession) -> uuid.UUID:
    run = AgentRun(issue_url=issue_url, status=RunStatus.RUNNING)
    session.add(run)
    await session.commit()

    client = get_llm_client()
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": TASK_TEMPLATE.format(issue_url=issue_url)},
    ]
    test_runs = 0
    passed = False

    for step_id in range(1, MAX_STEPS + 1):
        attempt = min(test_runs + 1, MAX_TEST_RUNS)
        context_snapshot = json.loads(json.dumps(messages))  # real context sent to the LLM
        step_tools = [TOOLS[0]] if step_id == 1 else TOOLS  # step 1: read-only
        started = time.perf_counter()
        try:
            reply = await client.chat(messages, step_tools)
        except Exception as exc:
            session.add(
                TraceStep(
                    run_id=run.id,
                    step_id=step_id,
                    input_context={"messages": context_snapshot, "tools": [t["function"]["name"] for t in step_tools]},
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
            raise

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
            recorded_calls.append({"name": call["name"], "args": call["arguments"], "result": result})
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
                input_context={"messages": context_snapshot, "tools": [t["function"]["name"] for t in step_tools]},
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
    return run.id
