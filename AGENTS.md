# AGENTS.md

DevPilot Agent (UI branded TraceForge) is a two-part app: a FastAPI backend (agent, traces, evals) and a Vite/React SPA (approval inbox).

## Layout

- `backend/src/main.py` — FastAPI `app`, `/health`, CORS middleware, and the `agent`, `traces`, `evals` routers (`backend/src/routers/`).
- `backend/src/agent/` — orchestration (`loop.py`: single-role `run_agent` for evals, multi-role `run_multi_agent`), one role's LLM cycle (`cycle.py`), prompts, tool schemas and per-role permissions (`tool_schemas.py`), tools on a per-run `Workspace` (`tools.py`), cost (`pricing.py`), background launcher with a single run slot (`executor.py`), demo repos (`demo_repos.py`), and the LLM abstraction (`llm/`).
- `backend/src/{models,schemas,db}/`, `backend/migrations/` (Alembic), `backend/sandbox/` (Dockerfile for the test sandbox), `backend/scripts/` (runners, `demo_data.py`), `backend/demo/runs.json` (recorded demo runs).
- `backend/tests/` — only `__init__.py` and `fixtures/repo/{sample.py,test_sample.py}`, the default fixture repo for the agent. Tool/guard unit tests live in `backend/tests/test_tools.py` (`make test`, 27 tests, no Docker or LLM needed).
- `evals/` — `cases/` (16 JSON cases), `fixtures/case_XX/`, `reports/`. Run with `make eval`.
- `frontend/` — Vite + React 19 in plain JavaScript/JSX (no TypeScript): the TraceForge approval inbox.

## Commands

Backend (run from `backend/`; the only environment is the repo-root `.venv`, using the Python of that venv):

```bash
cd backend && ../.venv/bin/uvicorn src.main:app --reload   # http://127.0.0.1:8000
curl http://127.0.0.1:8000/health
```

Infrastructure services (Postgres 18 on host port 5433, Redis 7 on port 6379, credentials devpilot/devpilot) are described in the root docker-compose.yml. Start them with docker compose up -d or podman compose up -d depending on your environment. During development they may already be running via Podman (podman start devpilot-postgres devpilot-redis).

Evals and sandbox (from the repo root; need Postgres/Redis up, e.g. `podman start devpilot-postgres devpilot-redis`, and a Docker daemon):

```bash
make sandbox-image   # builds devpilot-sandbox:latest used by run_tests
make eval            # runs all evals/cases, writes evals/reports/<timestamp>.json
make demo-seed       # loads the recorded demo runs (backend/demo/runs.json) into the database
```

Frontend (pnpm; `pnpm-lock.yaml` is authoritative):

```bash
cd frontend && pnpm install
pnpm dev      # http://localhost:5173
pnpm build
pnpm lint     # eslint . (JS/JSX only)
```

There is no frontend test script. Backend unit tests: `make test`. Pytest also runs inside the sandbox container against fixture repos (`run_tests`, `make eval`). CI: `.github/workflows/ci.yml`.

## Gotchas

- Backend dependencies are pinned in `backend/requirements.txt`; add new ones there. Config comes from `backend/.env` via pydantic-settings (never commit it, see Security).
- CORS in `backend/src/main.py` allows only `http://localhost:5173` and `http://127.0.0.1:5173`. `frontend/src/api.js` reads `VITE_API_URL` (default `http://127.0.0.1:8000`). Changing the API port or the frontend origin requires updating both sides.
- `backend/` is not a package (no `__init__.py`). Import as `src.*` when working from `backend/` (scripts need `PYTHONPATH=.`); prefer running from `backend/`.
- The frontend has no env-based config; all HTTP calls live in `frontend/src/api.js`.
- There is no formatter or typechecker. Runs are created from the UI (`POST /agent/runs`, one at a time) on demo repos taken from `evals/fixtures/`; cloning a GitHub issue/repo is not implemented (v1.1).
- Costs: `LLM_PRICE_INPUT_PER_MTOK` / `LLM_PRICE_OUTPUT_PER_MTOK` set the price; `gemini-3.1-flash-lite` is treated as free tier (cost 0, `cost_basis: free_tier` in eval reports); any other model without prices has cost `None`.
- Git history follows Conventional Commits with `backend`/`frontend` scopes, e.g. `feat(frontend): ...`.

## Restricciones del proyecto (no negociables)

**Objetivo:** Agente de código que recibe issues de GitHub, analiza el repo, genera parches, ejecuta tests, y se detiene antes de merge para aprobación humana. La tesis: "No me importa solo lo que hace el Agente, me importa cómo sé que se equivocó y cómo lo corregí."

**Stack:** FastAPI (async) + PostgreSQL + Redis + Docker sandbox + React/Vite. LLM con capa de abstracción (OpenAI/Claude). Django opcional para admin.

**Reglas duras:**
1. El Agente nunca hace merge. Siempre se detiene y espera aprobación humana.
2. Cada decisión persiste una traza con: `step_id`, `timestamp`, `agent_role`, `input_context` (contexto real, no solo prompt final), `tool_calls`, `reasoning_summary`, `outcome`.
3. `evals/` con al menos 15 casos ejecutables. `make eval` corre todos y genera informe con tasa de éxito, pasos, latencia p50/p95, costo por tarea.
4. Hito 3 (sandbox Docker, límites de permisos y auditoría de prompt injection) está **implementado en v1.00**. Hito 4 (multi-rol: Triage / Developer / Reviewer) **también forma parte de la v1.00** y está implementado (permisos por rol a nivel de herramientas ofrecidas, no a nivel de base de datos). La v1.00 no se considera terminada hasta que ambos hitos estén completos y exista el README.
5. Priorizar observabilidad y medición sobre "inteligencia". Agente simple con buenas trazas > Agente complejo sin métricas.

**Flujo v1.00 (implementado):** texto del issue + repo de demo (`POST /agent/runs` desde la UI) → Triage → Developer (máx 3 ejecuciones de tests) → Reviewer → se detiene en `awaiting_approval` → humano aprueba/rechaza.

**Flujo objetivo (v1.1, pendiente):** issue URL de GitHub → tarea en Redis → clonar repo → mismo ciclo multi-rol → PR en borrador → humano aprueba/rechaza.

**Estado actual:** v1.00 casi cerrada. Hitos 3 (sandbox) y 4 (multi-rol) implementados; falta commitear el README final. Ver "Definition of Done v1.00".

## Instrucciones para OpenCode
- Trabaja por hitos pequeños y verificables. No construyas todo de una vez.
- Antes de escribir código, propón el esquema de datos y espera mi confirmación.
- Cada herramienta nueva del Agente debe venir con al menos un caso de evaluación.
- Hito 3 (sandbox) ya está implementado. El hito 4 (multi-rol) se implementa antes de cerrar la v1.00; no lo adelantes sin que se pida el hito.

## Estado de hitos (v1.00)
- **Hito 3 — implementado:** `run_tests` corre en un contenedor Docker efímero (`--network=none`, 512 MB, 1 CPU, usuario no-root, repo montado solo lectura, timeout 60 s; imagen en `backend/sandbox/`, `make sandbox-image`); `propose_patch` solo escribe dentro de la copia temporal del fixture; el `TraceStep` registra el contenedor usado; `run_agent` audita el issue (`suspicious_issue` en `input_context`) sin bloquear.
- **Hito 4 — implementado:** Triage (`list_files`, `read_file`, `submit_triage`) → Developer (las cuatro herramientas) → Reviewer (`list_files`, `read_file`, `run_tests`, `submit_verdict`; sin `propose_patch`). `step_id` es global al run; no hay bucle Developer ↔ Reviewer. El veredicto del Reviewer vive en su `TraceStep`. Limitación: con Gemini Flash Lite el Reviewer aprueba casi todo.

## Definition of Done v1.00
- [x] Sandbox funcional (hito 3).
- [x] Multi-rol funcional (hito 4).
- [x] Evals pasando (`make eval`, 16 casos, 16/16 con un solo rol). El multi-rol se verificó solo con smoke tests de 2 casos (cuota del modelo gratuito).
- [x] UI de aprobación (bandeja de runs con timeline, approve/reject).
- [ ] README final (escrito; pendiente de commit).

## Security
- Postgres y Redis en `docker-compose.yml` solo escuchan en `127.0.0.1`. La API no tiene autenticación todavía: no la expongas fuera de localhost.
- `backend/.env` está en `.gitignore` y nunca ha sido trackeado (auditado sobre todo el historial). Contiene `LLM_API_KEY`; no se commitea ni se imprime.
- `CLAUDE.md` está en `.gitignore` (es para Claude Code, no para el repo).
- El sandbox de `run_tests` corre con `--network=none`, `--read-only`, usuario no-root y timeout de 60 s (además de 512 MB, 1 CPU, `--cap-drop=ALL`, repo montado solo lectura).
- `propose_patch` rechaza archivos de test (`test_*.py`, `*_test.py`, `conftest.py`) y solo escribe dentro de la copia temporal del fixture (path traversal, rutas absolutas y symlinks fuera de la copia bloqueados).
- La auditoría de prompt injection registra `suspicious_issue` en el `input_context` del primer `TraceStep`, pero no bloquea: es auditoría, no filtro.
