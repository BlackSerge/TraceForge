"""One role's LLM cycle: calls the model, executes the offered tools, persists a TraceStep per step."""
import json
import time
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from src.agent import tools
from src.agent.tool_schemas import DECISION_TOOLS, READ_ONLY_TOOLS, ROLE_TOOLS, TOOLS_BY_NAME
from src.agent.tools import Workspace
from src.models.run import AgentRun
from src.models.trace import StepOutcome, TraceStep

MAX_TEST_RUNS = 3  # also caps the `attempt` counter stored in traces

TOOL_FUNCS = {
    "list_files": tools.list_files,
    "read_file": tools.read_file,
    "propose_patch": tools.propose_patch,
    "run_tests": tools.run_tests,
}


async def _execute(ws: Workspace, name: str, args: dict) -> dict:
    func = TOOL_FUNCS.get(name)
    if func is None:
        return {"error": f"unknown tool: {name}"}
    args = {k: v for k, v in args.items() if k != "reasoning"}
    try:
        return await func(ws, **args)
    except Exception as exc:  # tool failures are data for the model, not crashes
        return {"error": f"{type(exc).__name__}: {exc}"}


def _input_context(messages: list, step_tools: list, step_id: int, suspicious: list[str]) -> dict:
    ctx = {"messages": messages, "tools": [t["function"]["name"] for t in step_tools]}
    if step_id == 1 and suspicious:
        ctx["suspicious_issue"] = True
        ctx["suspicious_patterns"] = suspicious
    return ctx


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
    ws: Workspace,
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
                result = await _execute(ws, name, args)
                if name == "run_tests" and "error" not in result:
                    test_runs += 1
                    last_tests = result
                    step_tests_passed = step_tests_passed or bool(result.get("passed"))
            had_error = had_error or "error" in result
            record = {"name": name, "args": args, "result": result}
            if name == "run_tests" and ws.last_sandbox and "error" not in result:
                record["sandbox"] = dict(ws.last_sandbox)
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
