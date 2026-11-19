# AGENTS.md

DevPilot Agent is an early-stage two-part app: a FastAPI backend and a Vite/React SPA. There is no root README, CI, formatter, typechecker, or backend dependency manifest yet — don't go looking for them.

## Layout

- `backend/src/main.py` — the entire backend today: one `app`, `/health` endpoint, CORS middleware.
- `backend/tests/` — empty (`__init__.py` only); no test runner is installed or configured.
- `frontend/` — Vite + React 19 in plain JavaScript/JSX (no TypeScript).

## Commands

Backend (run from `backend/`; the only environment is the repo-root `.venv`, Python 3.14):

```bash
cd backend && ../.venv/bin/uvicorn src.main:app --reload   # http://127.0.0.1:8000
curl http://127.0.0.1:8000/health
```

Frontend (pnpm; `pnpm-lock.yaml` is authoritative):

```bash
cd frontend && pnpm install
pnpm dev      # http://localhost:5173
pnpm build
pnpm lint     # eslint . (JS/JSX only)
```

There is no frontend test script and no backend test command.

## Gotchas

- Backend dependencies are undeclared. `.venv` also has SQLAlchemy, Alembic, asyncpg, redis, and pydantic-settings installed, but no code uses them. Don't assume database, models, migrations, or Redis wiring exists; create a manifest if you add dependencies.
- CORS in `backend/src/main.py` allows only `http://localhost:5173` and `http://127.0.0.1:5173`. `frontend/src/App.jsx` hardcodes `http://127.0.0.1:8000/health`. Changing either port or origin requires updating both files.
- `backend/` is not a package (no `__init__.py`). Import as `src.main` when working from `backend/`, or `backend.src.main` from the repo root; prefer running uvicorn from `backend/`.
- The frontend has no API client or env-based config — fetches are written inline in components.
- Git history follows Conventional Commits with `backend`/`frontend` scopes, e.g. `feat(frontend): ...`.



## Restricciones del proyecto (no negociables)

**Objetivo:** Agente de código que recibe issues de GitHub, analiza el repo, genera parches, ejecuta tests, y se detiene antes de merge para aprobación humana. La tesis: "No me importa solo lo que hace el Agente, me importa cómo sé que se equivocó y cómo lo corregí."

**Stack:** FastAPI (async) + PostgreSQL + Redis + Docker sandbox + React/Vite. LLM con capa de abstracción (OpenAI/Claude). Django opcional para admin.

**Reglas duras:**
1. El Agente nunca hace merge. Siempre se detiene y espera aprobación humana.
2. Cada decisión persiste una traza con: `step_id`, `timestamp`, `agent_role`, `input_context` (contexto real, no solo prompt final), `tool_calls`, `reasoning_summary`, `outcome`.
3. `evals/` con al menos 15 casos ejecutables. `make eval` corre todos y genera informe con tasa de éxito, pasos, latencia p50/p95, costo por tarea.
4. Hito 3 (sandbox Docker, límites de permisos y auditoría de prompt injection) está **implementado en v1.00**. Hito 4 (multi-rol: Triage / Developer / Reviewer) **también forma parte de la v1.00** y está pendiente; hasta entonces `agent_role` existe pero hay un solo rol. La v1.00 no se considera terminada hasta que ambos hitos estén completos.
5. Priorizar observabilidad y medición sobre "inteligencia". Agente simple con buenas trazas > Agente complejo sin métricas.

**Flujo v1:** issue URL → tarea en Redis → Agente cicla (read_file → propose_patch → run_tests, máx 3 reintentos) → se detiene → PR en borrador → humano aprueba/rechaza.

**Primer hito (lo que toca ahora):** modelos SQLAlchemy para `trace` y `eval`, esquema de base de datos, routers FastAPI vacíos. Sin lógica de Agente todavía.

## Instrucciones para OpenCode
- Trabaja por hitos pequeños y verificables. No construyas todo de una vez.
- Antes de escribir código, propón el esquema de datos y espera mi confirmación.
- Cada herramienta nueva del Agente debe venir con al menos un caso de evaluación.
- Hito 3 (sandbox) ya está implementado. El hito 4 (multi-rol) se implementa antes de cerrar la v1.00; no lo adelantes sin que se pida el hito.

## Estado de hitos (v1.00)
- **Hito 3 — implementado:** `run_tests` corre en un contenedor Docker efímero (`--network=none`, 512 MB, 1 CPU, usuario no-root, repo montado solo lectura, timeout 60 s; imagen en `backend/sandbox/`, `make sandbox-image`); `propose_patch` solo escribe dentro de la copia temporal del fixture; el `TraceStep` registra el contenedor usado; `run_agent` audita el issue (`suspicious_issue` en `input_context`) sin bloquear.
- **Hito 4 — pendiente (parte de v1.00):** roles Triage / Developer / Reviewer sobre el `agent_role` ya existente.

## Definition of Done v1.00
- [x] Sandbox funcional (hito 3).
- [ ] Multi-rol funcional (hito 4).
- [ ] Evals pasando (`make eval`, ≥15 casos; hoy 16/16 con un solo rol; debe repetirse con multi-rol).
- [x] UI de aprobación (bandeja de runs con timeline, approve/reject).
- [ ] README final.
