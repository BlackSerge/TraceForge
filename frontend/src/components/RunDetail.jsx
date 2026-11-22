import { useEffect, useState } from "react";
import { AlertTriangle, ArrowLeft, CheckCircle, FileText, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { approveRun, getRun, rejectRun } from "../api";
import { Diff, Timeline } from "./Timeline";
import { formatDate } from "../format";
import { btn, btnGhost } from "../styles";
import { Callout, EmptyState, ErrorBanner, StatusBadge } from "./ui";

function reviewVerdict(steps) {
  const call = steps
    .filter((s) => s.agent_role === "reviewer")
    .flatMap((s) => s.tool_calls)
    .find((c) => c.name === "submit_verdict" && c.result && c.result.recorded);
  return call ? call.args : null;
}

function finalDiff(steps) {
  const patches = steps
    .flatMap((s) => s.tool_calls)
    .filter((c) => c.name === "propose_patch" && c.result && c.result.diff);
  return patches.length ? patches[patches.length - 1] : null;
}

export default function RunDetail({ runId, onBack }) {
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
  const verdict = run ? reviewVerdict(run.steps) : null;

  return (
    <section className="space-y-5">
      <button className={btnGhost} onClick={onBack}>
        <ArrowLeft className="size-4" aria-hidden="true" /> Back to list
      </button>
      <ErrorBanner message={!loading && result.error} />
      {loading && !run && (
        <div className="space-y-3" role="status" aria-label="Loading run">
          <div className="h-8 w-2/3 animate-pulse rounded-md bg-ink-200 dark:bg-white/10" />
          <div className="h-24 animate-pulse rounded-lg bg-ink-200 dark:bg-white/10" />
          <div className="h-40 animate-pulse rounded-lg bg-ink-200 dark:bg-white/10" />
          <p className="flex items-center justify-center gap-2 text-sm text-ink-500">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading…
          </p>
        </div>
      )}
      {run && (
        <>
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="min-w-0 font-mono text-base font-semibold break-all">{run.issue_url}</h2>
              <StatusBadge status={run.status} />
            </div>
            <p className="font-mono text-xs break-all text-ink-500">
              Run {run.id} · created {formatDate(run.created_at)} · finished {formatDate(run.finished_at)}
            </p>
          </div>

          {run.rejection_reason && (
            <Callout tone="bad" icon={XCircle} title={run.status === "failed" ? "Failure reason" : "Reason for rejection"}>
              {run.rejection_reason}
            </Callout>
          )}
          {verdict && (
            <Callout
              tone={verdict.verdict === "approved" ? "ok" : "warn"}
              icon={verdict.verdict === "approved" ? ShieldCheck : AlertTriangle}
              title={`Reviewer verdict: ${verdict.verdict.replace("_", " ")}`}
            >
              {verdict.reason}
            </Callout>
          )}

          {run.status === "awaiting_approval" && (
            <div className="space-y-3 rounded-xl border border-ink-200 bg-white p-4 dark:border-white/10 dark:bg-ink-900">
              <ErrorBanner message={actionError} />
              <div className="flex flex-wrap gap-2">
                <button
                  className={`${btn} bg-green-600 text-white hover:bg-green-700 dark:bg-green-500 dark:text-ink-950 dark:hover:bg-green-400`}
                  disabled={busy}
                  onClick={() => decide(() => approveRun(run.id))}
                >
                  <CheckCircle className="size-4" aria-hidden="true" /> Approve
                </button>
                {!rejecting && (
                  <button
                    className={`${btn} border border-red-300 text-red-700 hover:bg-red-50 dark:border-red-500/40 dark:text-red-300 dark:hover:bg-red-950`}
                    disabled={busy}
                    onClick={() => setRejecting(true)}
                  >
                    <XCircle className="size-4" aria-hidden="true" /> Reject
                  </button>
                )}
              </div>
              {rejecting && (
                <div className="space-y-2">
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Reason for rejection (optional)"
                    rows={3}
                    className="w-full rounded-md border border-ink-200 bg-white p-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-forge-500 dark:border-white/10 dark:bg-ink-950"
                  />
                  <div className="flex gap-2">
                    <button
                      className={`${btn} bg-red-600 text-white hover:bg-red-700 dark:bg-red-500 dark:text-ink-950 dark:hover:bg-red-400`}
                      disabled={busy}
                      onClick={() => decide(() => rejectRun(run.id, reason))}
                    >
                      Confirm rejection
                    </button>
                    <button className={btnGhost} disabled={busy} onClick={() => setRejecting(false)}>
                      Cancel
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="space-y-2">
            <h3 className="text-sm font-semibold tracking-wide text-ink-500 uppercase">Proposed change</h3>
            {patch ? (
              <Diff text={patch.result.diff} />
            ) : (
              <EmptyState icon={FileText}>The agent did not propose any patch.</EmptyState>
            )}
          </div>

          <div className="space-y-3">
            <h3 className="text-sm font-semibold tracking-wide text-ink-500 uppercase">
              Timeline ({run.steps.length} {run.steps.length === 1 ? "step" : "steps"})
            </h3>
            <Timeline steps={run.steps} />
          </div>
        </>
      )}
    </section>
  );
}
