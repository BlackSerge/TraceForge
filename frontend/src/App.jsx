import { useState } from "react";
import { Hammer } from "lucide-react";
import RunDetail from "./components/RunDetail";
import RunList from "./components/RunList";

function App() {
  const [view, setView] = useState("list");
  const [selectedRunId, setSelectedRunId] = useState(null);

  return (
    <div className="min-h-screen bg-ink-50 font-sans text-ink-800 transition-colors dark:bg-ink-950 dark:text-ink-100">
      <header className="border-b border-ink-200 bg-white dark:border-white/10 dark:bg-ink-900">
        <div className="mx-auto flex max-w-5xl items-center gap-2.5 px-4 py-3 sm:px-6">
          <span className="grid size-8 place-items-center rounded-lg bg-forge-600 text-white">
            <Hammer className="size-4" aria-hidden="true" />
          </span>
          <h1 className="text-base font-semibold tracking-tight">
            TraceForge <span className="font-normal text-ink-500">· Approval Inbox</span>
          </h1>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-6 sm:px-6">
        {view === "list" ? (
          <RunList
            onSelect={(id) => {
              setSelectedRunId(id);
              setView("detail");
            }}
          />
        ) : (
          <RunDetail runId={selectedRunId} onBack={() => setView("list")} />
        )}
      </main>
    </div>
  );
}

export default App;
