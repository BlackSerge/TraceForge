import { useEffect, useState } from "react";
import { approveRun, getRun, listRuns, rejectRun } from "./api";
import "./App.css";

const STATUSES = ["awaiting_approval", "approved", "rejected", "failed", "running", "pending"];

function formatDate(value) {
  return value ? new Date(value).toLocaleString("en-US") : "—";
}

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{status.replace("_", " ")}</span>;
}

function ErrorBanner({ message }) {
  return message ? <p className="error" role="alert">Error: {message}</p> : null;
}

function Diff({ text }) {
  return (
    <pre className="diff">
      {text.split("\n").map((line, i) => {
        let cls = "";
        if (line.startsWith("+") && !line.startsWith("+++")) cls = "add";
        else if (line.startsWith("-") && !line.startsWith("---")) cls = "del";
        else if (line.startsWith("@@")) cls = "hunk";
        return (
          <span key={i} className={cls}>
            {line}
            {"\n"}
          </span>
        );
      })}
    </pre>
  );
}

function ToolCall({ call }) {
  const { name, args = {}, result = {} } = call;
  const argText = Object.entries(args)
    .filter(([k]) => k !== "reasoning" && k !== "new_content")
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return (
    <div className="tool-call">
      <code>
        {name}({argText})
      </code>
      {result.error && <p className="error">{result.error}</p>}
      {name === "read_file" && result.content !== undefined && <pre>{result.content}</pre>}
      {name === "propose_patch" && result.diff !== undefined && <Diff text={result.diff} />}
      {name === "run_tests" && result.passed !== undefined && (
        <>
          <p className={result.passed ? "ok" : "bad"}>tests {result.passed ? "passed" : "failed"}</p>
          <pre>{result.output}</pre>
        </>
      )}
    </div>
  );
}

function Timeline({ steps }) {
  return (
    <ol className="timeline">
      {steps.map((step) => (
        <li key={step.id} className={`step step-${step.outcome}`}>
          <div className="step-head">
            <strong>Step {step.step_id}</strong>
            <span className={`badge badge-outcome-${step.outcome}`}>{step.outcome}</span>
            <span className="muted">
              {step.latency_ms ?? "?"} ms · {step.tokens_in ?? "?"}→{step.tokens_out ?? "?"} tokens · {step.model ?? "?"}
            </span>
          </div>
          {step.reasoning_summary && <p className="reasoning">{step.reasoning_summary}</p>}
          {step.tool_calls.map((call, i) => (
            <ToolCall key={i} call={call} />
          ))}
        </li>
      ))}
    </ol>
  );
}

function finalDiff(steps) {
  const patches = steps
    .flatMap((s) => s.tool_calls)
    .filter((c) => c.name === "propose_patch" && c.result && c.result.diff);
  return patches.length ? patches[patches.length - 1] : null;
}

function RunList({ onSelect }) {
  const [filter, setFilter] = useState("awaiting_approval");
  const [result, setResult] = useState({ key: null, runs: [], error: null });

  useEffect(() => {
    let cancelled = false;
    listRuns(filter)
      .then((runs) => !cancelled && setResult({ key: filter, runs, error: null }))
      .catch((err) => !cancelled && setResult({ key: filter, runs: [], error: err.message }));
    return () => {
      cancelled = true;
    };
  }, [filter]);

  const loading = result.key !== filter;
  return (
    <section>
      <div className="toolbar">
        <h2>Runs</h2>
        <label>
          Status{" "}
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">all</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
      </div>
      <ErrorBanner message={!loading && result.error} />
      {loading && <p className="muted">Loading…</p>}
      {!loading && !result.error && result.runs.length === 0 && <p className="muted">No runs with this status.</p>}
      {!loading && result.runs.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Issue</th>
              <th>Status</th>
              <th>Created</th>
              <th>Finished</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {result.runs.map((run) => (
              <tr key={run.id}>
                <td>{run.issue_url}</td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>{formatDate(run.created_at)}</td>
                <td>{formatDate(run.finished_at)}</td>
                <td>
                  <button onClick={() => onSelect(run.id)}>View details</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function RunDetail({ runId, onBack }) {
  const [version, setVersion] = useState(0);
  const [result, setResult] = useState({ key: null, run: null, error: null });
  const [actionError, setActionError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const key = `${runId}:${version}`;

  useEffect(() => {
    let cancelled = false;
    getRun(runId)
      .then((run) => !cancelled && setResult({ key, run, error: null }))
      .catch((err) => !cancelled && setResult({ key, run: null, error: err.message }));
    return () => {
      cancelled = true;
    };
  }, [runId, key]);

  async function decide(action) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
      setRejecting(false);
      setReason("");
      setVersion((v) => v + 1);
    } catch (err) {
      setActionError(err.message);
    } finally {
      setBusy(false);
    }
  }

  const loading = result.key !== key;
  const run = result.run;
  const patch = run ? finalDiff(run.steps) : null;

  return (
    <section>
      <button className="link" onClick={onBack}>
        ← Back to list
      </button>
      <ErrorBanner message={!loading && result.error} />
      {loading && !run && <p className="muted">Loading…</p>}
      {run && (
        <>
          <div className="toolbar">
            <h2>{run.issue_url}</h2>
            <StatusBadge status={run.status} />
          </div>
          <p className="muted">
            Run {run.id} · created {formatDate(run.created_at)} · finished {formatDate(run.finished_at)}
          </p>
          {run.rejection_reason && <p className="reason">Reason for rejection: {run.rejection_reason}</p>}

          {run.status === "awaiting_approval" && (
            <div className="actions">
              <ErrorBanner message={actionError} />
              <button className="approve" disabled={busy} onClick={() => decide(() => approveRun(run.id))}>
                Approve
              </button>{" "}
              {!rejecting && (
                <button className="reject" disabled={busy} onClick={() => setRejecting(true)}>
                  Reject
                </button>
              )}
              {rejecting && (
                <div className="reject-form">
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Reason for rejection (optional)"
                    rows={3}
                  />
                  <button className="reject" disabled={busy} onClick={() => decide(() => rejectRun(run.id, reason))}>
                    Confirm rejection
                  </button>{" "}
                  <button disabled={busy} onClick={() => setRejecting(false)}>
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}

          <h3>Proposed change</h3>
          {patch ? <Diff text={patch.result.diff} /> : <p className="muted">The agent did not propose any patch.</p>}

          <h3>Timeline ({run.steps.length} {run.steps.length === 1 ? "step" : "steps"})</h3>
          <Timeline steps={run.steps} />
        </>
      )}
    </section>
  );
}

function App() {
  const [view, setView] = useState("list");
  const [selectedRunId, setSelectedRunId] = useState(null);

  return (
    <main className="app">
      <h1>TraceForge · Approval Inbox</h1>
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
  );
}

export default App;
