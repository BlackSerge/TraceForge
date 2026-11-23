A coding agent that shows its work: decision traces, automated evaluation, and human approval.

TraceForge takes a bug description and a repository, explores the code, proposes a patch, runs the tests in a sandbox, and stops. A person reviews the trace and approves or rejects the result. The agent never merges.

## What it is / Why it exists

Coding agents are usually judged by what they produce. The harder question is how you know when one was wrong, and how you correct it. When an agent acts and nobody can see why, a bad patch looks the same as a good one until it breaks something.

TraceForge attacks that with three mechanisms:

- **Decision traces.** Every step is stored with the real context sent to the model, the tool calls, a reasoning summary and the outcome.
- **Automated evaluation.** A harness of 16 executable cases measures success rate, steps, latency and cost, so a change to a prompt or a tool is compared with data instead of impressions.
- **Human approval.** A run ends in `awaiting_approval`. The agent has no merge capability; a person decides in the web inbox.

**Scope of this version (v1.00).** You describe a bug in the UI and pick one of the demo repositories (the fixtures behind the eval cases). Fetching an issue from GitHub and cloning a real repository are not implemented yet; see the roadmap.

## How it works

Three roles run in sequence, each with its own prompt and its own tool permissions:

1. **Triage** (`list_files`, `read_file`, `submit_triage`): decides `viable` or `not_viable`. If `not_viable`, the run ends as `failed` with the reason stored.
2. **Developer** (`list_files`, `read_file`, `propose_patch`, `run_tests`): edits the code in a temporary copy of the repo and runs the tests, up to 3 test runs.
3. **Reviewer** (`list_files`, `read_file`, `run_tests`; no `propose_patch`): receives the final diff and the last test result, and submits `approved` or `changes_requested` with a reason.
4. **Human**: the run waits in `awaiting_approval`, even when the Reviewer requests changes. There is no Developer/Reviewer loop; the person decides.

```
issue --> Triage --viable--> Developer --tests pass--> Reviewer --> awaiting_approval --> human
              |                  |                                                        approve / reject
              +-not_viable-> failed   +-tests never pass-> failed
```

Permissions are enforced at the tool level: a role can only call the tools it is offered, and a call to any other tool returns an error.

## Screenshots

A tour of the approval inbox, in the order a reviewer uses it.

### 1. Approval inbox: pick a run

![Approval inbox listing runs filtered by the awaiting approval status, with status badges and a View details button per row](docs/screenshots/run-list.png)

Every agent run is a row with its issue, a colored status badge (`awaiting approval`, `approved`, `rejected`, `failed`, `running`) and its timestamps. The **Status** filter opens on `awaiting approval`, the queue a human has to work through. **New run** opens the form to start a run on a demo repository, and each row has a delete button (disabled, with a tooltip, for runs in progress and runs that belong to an eval). On narrow screens the table becomes cards.

### 2. Run detail: verdict and proposed change

![Run detail with the reviewer verdict approving the patch, approve and reject buttons, and a red and green diff of calc.py](docs/screenshots/reviewer-verdict.png)

The top of a run answers "should this patch go in?". The green callout is the Reviewer's verdict and its reason (`approved` or `changes requested`). Below it are the **Approve** and **Reject** buttons (rejection takes an optional reason), and the **Proposed change**: the final diff, with removed lines in red and added lines in green. Approving only records the decision; nothing is merged.

### 3. Multi-role timeline: how the agent got there

![Timeline of a run: purple triage steps followed by blue developer steps, each with its tool calls and reasoning](docs/screenshots/run-detail.png)

Below the diff, the timeline lists every step of the run with its role: **Triage** in purple, **Developer** in blue, **Reviewer** in orange. Each step shows its outcome (`success`, `retry`, `error`), latency, tokens, model, the reasoning the agent gave for the call, and the tool call itself. File contents and test output are collapsed behind "Show file content" and "Show test output". This is the decision trace the project is about: when a patch is wrong, this is where you see what the agent read, ran and decided.

## Evaluation results

All runs use `gemini-3.1-flash-lite`. Reports are in `evals/reports/`.

| Version | Setup | Cases | Success | Avg steps | p50 | p95 |
|---|---|---|---|---|---|---|
| v1 | Single role, host pytest | 15 | 93.3% | 4.73 | 31.9 s | 247 s |
| v2 | + `list_files` tool, host pytest | 16 | 100% | 6.38 | 16.1 s | 44.4 s |
| v2 + sandbox | Same agent, tests in Docker | 16 | 100% | 6.38 | 18.1 s | 83.2 s |
| v3 | Multi-role, smoke test | 2 | working | n/a | n/a | n/a |

- v1's single failure was a network timeout with no client-side limit. It was fixed with a 60 s request timeout and retries with backoff.
- v3 was run on `add-subtracts` and `list-files` only: Triage, Developer and Reviewer ran and both runs reached `awaiting_approval`. The full 16-case eval was not run with three roles. The Reviewer approved every patch it saw.
- **Cost.** `cost_usd` is computed per step from token usage and summed per run. `gemini-3.1-flash-lite` is treated as a free-tier model, so its cost is `0`, and reports mark it with `cost_basis: free_tier`: that zero is a billing fact, not a measure of how cheap the agent is. Set `LLM_PRICE_INPUT_PER_MTOK` and `LLM_PRICE_OUTPUT_PER_MTOK` to get real costs with a paid model; a model without a known price reports `null`. The reports above predate this and show `null`.

## Quick start

Requirements: Docker (or Podman with `podman compose`), Python 3.15, pnpm.

```bash
python3.15 -m venv .venv && .venv/bin/python -m pip install -r backend/requirements.txt
docker compose up -d                     # or: podman compose up -d  (Postgres 18 :5433, Redis 7 :6379)
cd backend && ../.venv/bin/python -m alembic upgrade head && cd ..
make sandbox-image                       # test sandbox image
cd backend && ../.venv/bin/python -m uvicorn src.main:app --reload   # API on :8000
cd frontend && pnpm install && pnpm dev                              # UI on :5173 (another terminal)
make eval                                # 16 cases (calls the LLM; 5 s pause between cases)
make test                                # 28 backend unit tests (no Docker or LLM needed)
```

Create `backend/.env` (it is git-ignored) from the template: `cp backend/.env.example backend/.env`, then set your key.

| Variable | Meaning |
|---|---|
| `LLM_PROVIDER` | `openai_compat` (default) |
| `LLM_API_KEY` | API key (required, stored as `SecretStr`) |
| `LLM_BASE_URL` | OpenAI-compatible endpoint, for example Gemini's `/v1beta/openai/` |
| `LLM_MODEL` | model name |
| `DATABASE_URL` | defaults to `postgresql+asyncpg://devpilot:devpilot@localhost:5433/devpilot` |
| `REDIS_URL` | defaults to `redis://localhost:6379/0` |
| `LLM_PRICE_INPUT_PER_MTOK`, `LLM_PRICE_OUTPUT_PER_MTOK` | optional, USD per 1M tokens, for cost accounting |

To try it: open the UI, click **New run**, pick a demo repository, edit the issue text if you want, and start. The run page refreshes while the agent works. Only one run can be active at a time, and a run needs a working `LLM_API_KEY`. Runs that are not in progress (and do not belong to an eval) can be deleted from the list.

## Architecture

- **FastAPI (async)** serves the inbox API; the agent loop is I/O-bound (LLM calls, Docker), so async fits. `POST /agent/runs` starts a run in the background and returns immediately.
- **SQLAlchemy async + Alembic + PostgreSQL 18** store runs, trace steps and eval results, with versioned migrations. Approval transitions are a conditional `UPDATE`, so two concurrent decisions cannot both win.
- **LLM abstraction** (`BaseLLMClient`) with an OpenAI-compatible client, retries on 429/503/timeout, and a stub for a native Google client. Switching providers does not touch the loop.
- **Agent core** (`backend/src/agent/`): `cycle.py` runs one role's LLM cycle and writes a `TraceStep` per step; `loop.py` orchestrates the roles; `tools.py` holds the tools, each working on a per-run `Workspace` (no global state); `pricing.py` computes cost.
- **Docker sandbox** runs `pytest` for the repository under test, so the host never executes it.
- **React 19 + Vite + Tailwind v4 + lucide-react** build the approval inbox. All HTTP calls live in `frontend/src/api.js`.
- **Redis** is provisioned in `docker-compose.yml` but not used by any code yet.

## Decision traces

Each `TraceStep` stores: `step_id` (global to the run), `timestamp`, `agent_role` (`triage`, `developer`, `reviewer`), `input_context` (the real messages and tool list sent to the model, not only the final prompt), `tool_calls` (arguments, results, and sandbox container metadata for test runs), `reasoning_summary`, `outcome` (`success`, `retry`, `error`, `stopped`), `attempt`, `tokens_in`, `tokens_out`, `cost_usd`, `latency_ms` and `model`.

This is the point of the project: when a patch is wrong, the trace shows what the agent saw, what it did and why it said it did it.

The run detail endpoint omits `input_context` because it grows with every step. Fetch it per step with `GET /agent/runs/{id}/steps/{n}`.

## Evaluation harness

`make eval` upserts the cases from `evals/cases/*.json`, copies each fixture from `evals/fixtures/` to a fresh temporary directory (so fixtures are reset on every run), runs the agent, then re-runs the tests itself instead of trusting the agent's trace. It stores an `EvalRun` in the database and writes `evals/reports/<timestamp>.json` with success rate, average steps, latency p50/p95, cost per task and its basis. A failing case never aborts the run. `python scripts/run_evals.py --only <slug>` runs a single case.

The 16 cases cover arithmetic, strings, lists, dictionaries, boundary conditions and multi-file bugs (one case needs `list_files` to find the faulty module). Evals use the single-role agent; the multi-role flow has only been smoke-tested.

## Security

- Tests run in a container with `--network=none`, `--read-only`, a non-root user, 512 MB, 1 CPU, `--cap-drop=ALL`, a 60 s timeout, and a base image pinned by digest.
- `propose_patch` refuses test files (so the agent cannot pass by editing tests) and blocks path traversal, absolute paths and escaping symlinks. `read_file` caps file size.
- Issue text is audited for suspicious patterns; matches set `suspicious_issue` in the first trace step. This is an audit, not a filter.
- `llm_api_key` is a `SecretStr`. CORS allows only the two local UI origins. Postgres and Redis bind to `127.0.0.1`. Runs left in `running` by a crashed process are marked `failed` at startup. Run creation is limited to one active run.

Known limitations:

- The API has no authentication (it binds to `127.0.0.1`): anyone who can reach it can create and approve runs.
- The backend talks to the Docker socket, which is equivalent to root on the host. Accepted for v1.
- Gemini Flash Lite is a permissive Reviewer and tends to approve every patch that passes the tests. There is no eval yet that measures whether the Reviewer catches a bad patch.

## Roadmap / known limitations

- GitHub issue URL as input: fetch the issue, clone the repository, open a draft PR; Redis queue and worker (v1.1).
- API authentication and a `decided_by` field.
- Run the full eval with the three roles, ideally also with a paid model.
- An eval case with a trap patch (for example one that hard-codes the expected value) to measure the Reviewer.
- Move Gemini's `thought_signature` handling into the LLM client.
- Frontend tests with Vitest, and a router for deep links.

## Tech stack

Python 3.15, FastAPI 0.162, Uvicorn 0.54, SQLAlchemy 2.1 (async) with asyncpg 0.32, Alembic 1.20, Pydantic 2.14, OpenAI SDK 3.52, pytest 9.2, PostgreSQL 18, Redis 7, Docker, React 19, Vite 8, Tailwind CSS 4, lucide-react.

## Repository structure

```
backend/src/agent/      roles, cycle, tools, prompts, pricing, executor, LLM clients (llm/)
backend/src/routers/    FastAPI routers: agent (runs, approval), traces, evals
backend/src/models/     SQLAlchemy models; schemas/ holds the Pydantic models
backend/migrations/     Alembic migrations
backend/sandbox/        Dockerfile of the test sandbox image
backend/scripts/        eval runner and multi-role smoke script
backend/tests/          unit tests (tool guards, CORS, pricing, demo repos)
evals/                  cases/ (JSON), fixtures/ (repos under test), reports/
frontend/src/           App.jsx, components/, styles.js, api.js
docs/screenshots/       images used in this README
.github/workflows/      CI: source hygiene, backend tests, frontend build
```

Some internal identifiers (the `devpilot` database, container and image names) keep the project's original name.

## License

MIT, see [LICENSE](LICENSE).
