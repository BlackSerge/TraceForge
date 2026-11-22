import { useEffect, useState } from "react";
import { ChevronRight, Clock, Inbox } from "lucide-react";
import { listRuns } from "../api";
import { formatDate } from "../format";
import { btnGhost } from "../styles";
import { EmptyState, ErrorBanner, ListSkeleton, StatusBadge } from "./ui";

const STATUSES = ["awaiting_approval", "approved", "rejected", "failed", "running", "pending"];

export default function RunList({ onSelect }) {
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
    <section className="space-y-4" aria-live="polite" aria-busy={loading}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold">Runs</h2>
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
      {loading && <ListSkeleton />}
      {!loading && !result.error && result.runs.length === 0 && (
        <EmptyState icon={Inbox}>No runs with this status.</EmptyState>
      )}

      {!loading && result.runs.length > 0 && (
        <>
          {/* desktop: table */}
          <div className="hidden overflow-hidden rounded-xl border border-ink-200 bg-white md:block dark:border-white/10 dark:bg-ink-900">
            <table className="w-full text-left text-sm">
              <thead className="bg-ink-50 text-xs tracking-wide text-ink-500 uppercase dark:bg-white/5">
                <tr>
                  <th scope="col" className="px-4 py-2.5 font-medium">Issue</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Created</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">Finished</th>
                  <th scope="col" className="px-4 py-2.5"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-ink-200 dark:divide-white/10">
                {result.runs.map((run) => (
                  <tr key={run.id} className="transition-colors hover:bg-ink-50 dark:hover:bg-white/5">
                    <td className="max-w-xs truncate px-4 py-3 font-mono text-xs">{run.issue_url}</td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3 whitespace-nowrap text-ink-500">{formatDate(run.created_at)}</td>
                    <td className="px-4 py-3 whitespace-nowrap text-ink-500">{formatDate(run.finished_at)}</td>
                    <td className="px-4 py-3 text-right">
                      <button className={btnGhost} onClick={() => onSelect(run.id)}>
                        View details <ChevronRight className="size-4" aria-hidden="true" />
                      </button>
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
                  <p className="min-w-0 font-mono text-xs break-all">{run.issue_url}</p>
                  <StatusBadge status={run.status} />
                </div>
                <p className="flex items-center gap-1.5 text-xs text-ink-500">
                  <Clock className="size-3.5" aria-hidden="true" />
                  <span className="sm:hidden">{formatDate(run.created_at)}</span>
                  <span className="hidden sm:inline">
                    {formatDate(run.created_at)} → {formatDate(run.finished_at)}
                  </span>
                </p>
                <button className={`${btnGhost} w-full`} onClick={() => onSelect(run.id)}>
                  View details <ChevronRight className="size-4" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
