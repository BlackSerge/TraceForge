import { AlertTriangle, Loader2 } from "lucide-react";
import { ROLE_STYLES, STATUS_STYLES } from "../styles";

export function StatusBadge({ status }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset transition-colors ${STATUS_STYLES[status] ?? STATUS_STYLES.pending}`}
    >
      {status.replace("_", " ")}
    </span>
  );
}

export function RoleBadge({ role }) {
  const style = ROLE_STYLES[role] ?? ROLE_STYLES.developer;
  const Icon = style.icon;
  return (
    <span className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ${style.badge}`}>
      <Icon className="size-3.5" aria-hidden="true" />
      {role}
    </span>
  );
}

export function ErrorBanner({ message }) {
  if (!message) return null;
  return (
    <div
      role="alert"
      className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-950 dark:text-red-200"
    >
      <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>Error: {message}</span>
    </div>
  );
}

export function Callout({ tone, icon: Icon, title, children }) {
  const tones = {
    ok: "border-green-300 bg-green-50 text-green-900 dark:border-green-500/30 dark:bg-green-950 dark:text-green-200",
    warn: "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-500/30 dark:bg-amber-950 dark:text-amber-200",
    bad: "border-red-300 bg-red-50 text-red-900 dark:border-red-500/30 dark:bg-red-950 dark:text-red-200",
  };
  return (
    <div className={`flex gap-3 rounded-lg border p-4 transition-colors ${tones[tone]}`}>
      <Icon className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div className="min-w-0 text-sm">
        <p className="font-semibold">{title}</p>
        <p className="mt-0.5 break-words">{children}</p>
      </div>
    </div>
  );
}

export function EmptyState({ icon: Icon, children, spin }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-ink-300 px-6 py-16 text-center text-ink-500 dark:border-white/15">
      <Icon className={`size-8 ${spin ? "animate-spin" : ""}`} aria-hidden="true" />
      <p className="text-sm">{children}</p>
    </div>
  );
}

export function ListSkeleton() {
  return (
    <div className="space-y-3" role="status" aria-label="Loading runs">
      {[0, 1, 2].map((i) => (
        <div key={i} className="h-14 animate-pulse rounded-lg bg-ink-200 dark:bg-white/10" />
      ))}
      <p className="flex items-center justify-center gap-2 pt-2 text-sm text-ink-500">
        <Loader2 className="size-4 animate-spin" aria-hidden="true" /> Loading…
      </p>
    </div>
  );
}
