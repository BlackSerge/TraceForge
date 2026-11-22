# TraceForge frontend

Approval inbox for the DevPilot agent: list runs, inspect the multi-role timeline (triage / developer / reviewer), and approve or reject. Vite + React 19 (plain JS) + Tailwind CSS v4 + lucide-react.

```bash
pnpm install
pnpm dev     # http://localhost:5173
pnpm build
pnpm lint
```

The backend URL comes from `VITE_API_URL` (default `http://127.0.0.1:8000`). The backend CORS allows only `http://localhost:5173` and `http://127.0.0.1:5173`.

Layout: `src/App.jsx` (view state + layout), `src/components/` (RunList, RunDetail, Timeline, ui, ErrorBoundary), `src/styles.js` (design tokens), `src/format.js`, `src/api.js` (all HTTP calls).
