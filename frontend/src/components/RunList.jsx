import { useEffect, useState } from "react";
import { ChevronRight, Clock, Inbox, Plus, Trash2 } from "lucide-react";
import { deleteRun, listRuns } from "../api";
import { formatDate } from "../format";
import { btn, btnGhost } from "../styles";
import { EmptyState, ErrorBanner, ListSkeleton, StatusBadge } from "./ui";

const STATUSES = ["awaiting_approval", "approved", "rejected", "failed", "running", "pending"];

const POLL_MS = 5000;

// Why a run cannot be deleted (the API refuses these), or null when it can.
function deleteBlockedReason(run) {
  if (run.status === "running" || run.status === "pending") return "Cannot delete a run in progress";
  if (run.eval_run_id) return "Part of an eval run: cannot be deleted";
  return null;
}

// Always rendered, so every row keeps the same layout; disabled (with the reason) when not allowed.
function DeleteButton({ run, onDelete }) {
  const blocked = deleteBlockedReason(run);
  return (
    <button
      className={`${btnGhost} shrink-0`}
      onClick={() => onDelete(run)}
      disabled={blocked !== null}
      aria-label="Delete run"
      title={blocked ?? "Delete run"}
    >
      <Trash2 className="size-4" aria-hidden="true" />
    </button>
  );
}

function issueLabel(run) {
  return run.issue_text ?? run.issue_url;
}

export default function RunList({ onSelect, onNew }) {
  const [filter, setFilter] = useState("awaiting_approval");
  const [result, setResult] = useState({ key: null, runs: [], error: null });
  const [tick, setTick] = useState(0);
  const [deleteError, setDeleteError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    listRuns(filter)
      .then((runs) => !cancelled && setResult({ key: filter, runs, error: null }))
      .catch((err) => !cancelled && setResult({ key: filter, runs: [], error: err.message }));
    return () => {
      cancelled = true;
    };
  }, [filter, tick]);

  // refresh while a run is still in progress
  const inProgress = result.runs.some((r) => r.status === "running" || r.status === "pending");
  useEffect(() => {
    if (!inProgress) return undefined;
    const id = setInterval(() => setTick((t) => t + 1), POLL_MS);
    return () => clearInterval(id);
  }, [inProgress]);

  const loading = result.key !== filter;

  async function remove(run) {
    if (!window.confirm("Delete this run and its trace? This cannot be undone.")) return;
    setDeleteError(null);
    try {
      await deleteRun(run.id);
      setTick((t) => t + 1);
    } catch (err) {
      setDeleteError(err.message);
    }
  }
  return (
    <section className="space-y-4" aria-live="polite" aria-busy={loading}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="text-lg font-semibold">Runs</h2>
          <button className={`${btn} bg-forge-600 text-white hover:bg-forge-700`} onClick={onNew}>
            <Plus className="size-4" aria-hidden="true" /> New run
          </button>
        </div>
        <label className="flex items-center gap-2 text-sm text-ink-500">
          Status
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="rounded-md border border-ink-200 bg-white px-2 py-1.5 text-sm text-ink-800 transition-colors focus-visible:outline-2 focus-visible:outline-forge-500 dark:border-white/10 dark:bg-ink-900 dark:text-ink-100"
          >
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
      <ErrorBanner message={deleteError} />
      {loading && <ListSkeleton />}
      {!loading && !result.error && result.runs.length === 0 && (
        <EmptyState icon={Inbox}>No runs with this status.</EmptyState>
      )}

      {!loading && result.runs.length > 0 && (
        <>
          {/* desktop: table */}
          <div className="hidden overflow-x-auto rounded-xl border border-ink-200 bg-white md:block dark:border-white/10 dark:bg-ink-900">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-50 text-xs tracking-wide text-ink-500 uppercase dark:bg-white/5">
                <tr>
                  <th scope="col" className="px-3 py-2.5 font-medium">Issue</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Status</th>
                  <th scope="col" className="px-3 py-2.5 font-medium">Created</th>
                  <th scope="col" className="hidden px-3 py-2.5 font-medium lg:table-cell">Finished</th>
                  <th scope="col" className="px-3 py-2.5"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200 dark:divide-white/10">
                {result.runs.map((run) => (
                  <tr key={run.id} className="transition-colors hover:bg-ink-50 dark:hover:bg-white/5">
                    <td className="w-full max-w-0 truncate px-3 py-3 text-xs" title={issueLabel(run)}>{issueLabel(run)}</td>
                    <td className="px-3 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-3 py-3 whitespace-nowrap text-ink-500">{formatDate(run.created_at)}</td>
                    <td className="hidden px-3 py-3 whitespace-nowrap text-ink-500 lg:table-cell">{formatDate(run.finished_at)}</td>
                    <td className="w-px px-3 py-3 text-right whitespace-nowrap">
                      <div className="flex justify-end gap-2">
                        <button className={`${btnGhost} whitespace-nowrap`} onClick={() => onSelect(run.id)}>
                          View details <ChevronRight className="size-4" aria-hidden="true" />
                        </button>
                        <DeleteButton run={run} onDelete={remove} />
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* mobile: cards */}
          <ul className="space-y-3 md:hidden">
            {result.runs.map((run) => (
              <li
                key={run.id}
                className="space-y-3 rounded-xl border border-ink-200 bg-white p-4 transition-colors dark:border-white/10 dark:bg-ink-900"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="min-w-0 text-xs break-words">{issueLabel(run)}</p>
                  <StatusBadge status={run.status} />
                </div>
                <p className="flex items-center gap-1.5 text-xs text-ink-500">
                  <Clock className="size-3.5" aria-hidden="true" />
                  <span className="sm:hidden">{formatDate(run.created_at)}</span>
                  <span className="hidden sm:inline">
                    {formatDate(run.created_at)} → {formatDate(run.finished_at)}
                  </span>
                </p>
                <div className="flex gap-2">
                  <button className={`${btnGhost} flex-1`} onClick={() => onSelect(run.id)}>
                    View details <ChevronRight className="size-4" aria-hidden="true" />
                  </button>
                  <DeleteButton run={run} onDelete={remove} />
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
