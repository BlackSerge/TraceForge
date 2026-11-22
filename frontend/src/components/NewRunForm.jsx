import { useEffect, useState } from "react";
import { ArrowLeft, Loader2, Play } from "lucide-react";
import { createRun, listDemoRepos } from "../api";
import { btn, btnGhost } from "../styles";
import { ErrorBanner } from "./ui";

const field =
  "w-full rounded-md border border-ink-200 bg-white p-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-forge-500 dark:border-white/10 dark:bg-ink-950";

export default function NewRunForm({ onBack, onCreated }) {
  const [repos, setRepos] = useState([]);
  const [repo, setRepo] = useState("");
  const [issue, setIssue] = useState("");
  const [loadError, setLoadError] = useState(null);
  const [submitError, setSubmitError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listDemoRepos()
      .then((list) => {
        if (cancelled) return;
        setRepos(list);
        if (list.length) {
          setRepo(list[0].slug);
          setIssue(list[0].example_issue);
        }
      })
      .catch((err) => !cancelled && setLoadError(err.message));
    return () => {
      cancelled = true;
    };
  }, []);

  function pickRepo(slug) {
    setRepo(slug);
    const found = repos.find((r) => r.slug === slug);
    if (found) setIssue(found.example_issue);
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setSubmitError(null);
    try {
      const run = await createRun(issue, repo);
      onCreated(run.id);
    } catch (err) {
      setSubmitError(err.message);
      setBusy(false);
    }
  }

  const current = repos.find((r) => r.slug === repo);
  return (
    <section className="space-y-5">
      <button className={btnGhost} onClick={onBack}>
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to list
      </button>
      <h2 className="text-lg font-semibold">New run</h2>
      <p className="text-sm text-ink-500">
        Pick a demo repository and describe the bug. Triage, Developer and Reviewer run one after the other; you review
        the result and approve or reject it. The agent never merges.
      </p>
      <ErrorBanner message={loadError} />
      <form onSubmit={submit} className="space-y-4">
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Demo repository</span>
          <select value={repo} onChange={(e) => pickRepo(e.target.value)} className={field} disabled={busy}>
            {repos.map((r) => (
              <option key={r.slug} value={r.slug}>
                {r.slug}
              </option>
            ))}
          </select>
          {current && <span className="block text-xs text-ink-500">{current.description}</span>}
        </label>
        <label className="block space-y-1 text-sm">
          <span className="font-medium">Issue text</span>
          <textarea
            value={issue}
            onChange={(e) => setIssue(e.target.value)}
            rows={5}
            minLength={10}
            maxLength={4000}
            required
            disabled={busy}
            className={field}
          />
          <span className="block text-xs text-ink-500">10 to 4000 characters. Only one run can be active at a time.</span>
        </label>
        <ErrorBanner message={submitError} />
        <button type="submit" disabled={busy || !repo} className={`${btn} bg-forge-600 text-white hover:bg-forge-700`}>
          {busy ? <Loader2 className="size-4 animate-spin" aria-hidden="true" /> : <Play className="size-4" aria-hidden="true" />}
          Start run
        </button>
      </form>
    </section>
  );
}
