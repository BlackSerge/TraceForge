# AGENTS.md

DevPilot Agent (UI branded TraceForge) is a two-part app: a FastAPI backend (agent, traces, evals) and a Vite/React SPA (approval inbox).

## Project constraints (non-negotiable)

**Goal:** a coding agent that analyzes a repository, proposes patches, runs the tests, and stops before merging so a human approves or rejects. The thesis: "I don't only care about what the agent does; I care about how I know it was wrong and how I corrected it."

**Stack:** FastAPI (async) + PostgreSQL + Redis + Docker sandbox + React/Vite. LLM behind an abstraction layer (OpenAI-compatible / Claude). Django optional for admin.

**Hard rules:**
1. The agent never merges. It always stops and waits for human approval.
2. Every decision persists a trace with: `step_id`, `timestamp`, `agent_role`, `input_context` (the real context, not only the final prompt), `tool_calls`, `reasoning_summary`, `outcome`.
3. `evals/` has at least 15 executable cases. `make eval` runs them all and writes a report with success rate, steps, latency p50/p95 and cost per task.
4. Prioritize observability and measurement over "intelligence". A simple agent with good traces beats a complex agent without metrics.

## Milestones (v1.00)

All four milestones are implemented. v1.00 is complete once the final README is committed (see Definition of Done).

| # | Milestone | What it covers |
|---|---|---|
| 1 | Persistence and API skeleton | SQLAlchemy models for traces and evals, database schema and migrations, FastAPI routers |
| 2 | Agent core and evaluation | agent loop with decision traces, LLM abstraction, tools (`list_files`, `read_file`, `propose_patch`, `run_tests`), eval harness (16 cases, `make eval`), approval inbox |
| 3 | Sandbox and hardening | tests run in an ephemeral Docker container (`--network=none`, 512 MB, 1 CPU, non-root, repo mounted read-only, 60 s timeout); `propose_patch` writes only inside a temporary copy; prompt-injection audit (`suspicious_issue` in the first `TraceStep`, never blocking) |
| 4 | Multi-role | Triage (`list_files`, `read_file`, `submit_triage`) → Developer (all four tools) → Reviewer (`list_files`, `read_file`, `run_tests`, `submit_verdict`; no `propose_patch`). `step_id` is global to the run; no Developer ↔ Reviewer loop. The reviewer's verdict lives in its `TraceStep`. Permissions are the tools offered to each role, not database-level permissions |

**Current flow (v1.00):** issue text + demo repository (`POST /agent/runs`, from the UI) → Triage → Developer (at most 3 test runs) → Reviewer → stops in `awaiting_approval` → human approves or rejects.

**Target flow (v1.1, not implemented):** GitHub issue URL → task in Redis → clone the repository → same multi-role cycle → draft PR → human approves or rejects.

Known limitation: with Gemini Flash Lite the Reviewer approves almost everything.

## Layout

- `backend/src/main.py` — FastAPI `app`, `/health`, CORS middleware, startup reaper for orphaned runs, and the `agent`, `traces`, `evals` routers (`backend/src/routers/`).
- `backend/src/agent/` — orchestration (`loop.py`: single-role `run_agent` for evals, multi-role `run_multi_agent`), one role's LLM cycle (`cycle.py`), prompts, tool schemas and per-role permissions (`tool_schemas.py`), tools on a per-run `Workspace` (`tools.py`), cost (`pricing.py`), background launcher with a single run slot (`executor.py`), demo repositories (`demo_repos.py`), and the LLM abstraction (`llm/`).
- `backend/src/{models,schemas,db}/`, `backend/migrations/` (Alembic), `backend/sandbox/` (Dockerfile of the test sandbox), `backend/scripts/` (runners).
- `backend/tests/` — unit tests (`make test`, 28 tests, no Docker or LLM needed).
- `evals/` — `cases/` (16 JSON cases), `fixtures/case_XX/`, `reports/`. Run with `make eval`. The fixtures are also the demo repositories offered by the UI.
- `frontend/` — Vite + React 19 in plain JavaScript/JSX (no TypeScript), Tailwind CSS v4, lucide-react: the TraceForge approval inbox.

## Commands

Backend (run from `backend/`; the only environment is the repo-root `.venv`, using the Python of that venv):

```bash
cd backend && ../.venv/bin/uvicorn src.main:app --reload   # http://127.0.0.1:8000
curl http://127.0.0.1:8000/health
```

Infrastructure services (Postgres 18 on host port 5433, Redis 7 on port 6379, credentials devpilot/devpilot) are described in the root `docker-compose.yml`. Start them with `docker compose up -d` or `podman compose up -d`. During development they may already be running via Podman (`podman start devpilot-postgres devpilot-redis`).

Evals and sandbox (from the repo root; need Postgres/Redis up and a Docker daemon):

```bash
make sandbox-image   # builds devpilot-sandbox:latest used by run_tests
make eval            # runs all evals/cases, writes evals/reports/<timestamp>.json
make test            # backend unit tests
```

Frontend (pnpm; `pnpm-lock.yaml` is authoritative):

```bash
cd frontend && pnpm install
pnpm dev      # http://localhost:5173
pnpm build
pnpm lint     # eslint . (JS/JSX only)
```

There is no frontend test script. Pytest also runs inside the sandbox container against fixture repositories (`run_tests`, `make eval`). CI: `.github/workflows/ci.yml`.

## Gotchas

- Backend dependencies are pinned in `backend/requirements.txt`; add new ones there. Config comes from `backend/.env` via pydantic-settings (template: `backend/.env.example`; never commit `.env`, see Security).
- CORS in `backend/src/main.py` allows only `http://localhost:5173` and `http://127.0.0.1:5173`. `frontend/src/api.js` reads `VITE_API_URL` (default `http://127.0.0.1:8000`). Changing the API port or the frontend origin requires updating both sides.
- `backend/` is not a package (no `__init__.py`). Import as `src.*` when working from `backend/` (scripts need `PYTHONPATH=.`); prefer running from `backend/`.
- All HTTP calls of the frontend live in `frontend/src/api.js`.
- Runs are created from the UI (`POST /agent/runs`, one at a time) on demo repositories taken from `evals/fixtures/`. Cloning a GitHub issue or repository is not implemented. Runs that belong to an eval run cannot be deleted from the UI.
- Costs: `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` set the price. `gemini-3.1-flash-lite` is treated as free tier (cost 0, `cost_basis: free_tier` in eval reports); any other model without prices has cost `None`.
- `run_agent` / `run_multi_agent` need an explicit `Workspace` (a temporary copy of a repository): `propose_patch` writes into it, so never point it at a tracked directory.
- There is no formatter or typechecker.
- Git history follows Conventional Commits with `backend`/`frontend` scopes, e.g. `feat(frontend): ...`.

## Security

- Postgres and Redis in `docker-compose.yml` listen only on `127.0.0.1`. The API has no authentication yet: do not expose it outside localhost.
- `backend/.env` is in `.gitignore` and has never been tracked (audited over the whole history). It holds `LLM_API_KEY`; never commit or print it.
- `CLAUDE.md` is in `.gitignore` (it is for Claude Code, not for the repository).
- The `run_tests` sandbox runs with `--network=none`, `--read-only`, a non-root user and a 60 s timeout (plus 512 MB, 1 CPU, `--cap-drop=ALL`, repository mounted read-only, base image pinned by digest).
- `propose_patch` rejects test files (`test_*.py`, `*_test.py`, `conftest.py`) and writes only inside the temporary copy of the fixture (path traversal, absolute paths and escaping symlinks are blocked).
- The prompt-injection audit records `suspicious_issue` in the `input_context` of the first `TraceStep`, but does not block: it is an audit, not a filter.
- The backend uses the Docker socket, which is equivalent to root on the host. Accepted for v1.

## Instructions for OpenCode and Claude

- Work in small, verifiable milestones. Do not build everything at once.
- Before writing code, propose the data schema and wait for confirmation.
- Every new agent tool ships with at least one evaluation case.
- Do not start a new milestone unless it is requested.

## Definition of Done v1.00

- [x] Functional sandbox (milestone 3).
- [x] Functional multi-role (milestone 4).
- [x] Evals passing (`make eval`, 16 cases, 16/16 with the single-role agent). Multi-role has only been smoke-tested on 2 cases (free-tier model quota).
- [x] Approval UI (run inbox with timeline, approve/reject, run creation and deletion).
- [ ] Final README (written; pending commit).
