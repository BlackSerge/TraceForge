// Design tokens shared by the components: Tailwind class strings and lucide icon maps.
import { CheckCircle, Code, Eye, FileText, FolderOpen, Play, Search, Wrench } from "lucide-react";

export const STATUS_STYLES = {
  awaiting_approval: "bg-amber-100 text-amber-800 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/30",
  approved: "bg-green-100 text-green-800 ring-green-600/20 dark:bg-green-400/10 dark:text-green-300 dark:ring-green-400/30",
  rejected: "bg-red-100 text-red-700 ring-red-600/20 dark:bg-red-400/10 dark:text-red-300 dark:ring-red-400/30",
  failed: "bg-red-200 text-red-900 ring-red-800/30 dark:bg-red-900/40 dark:text-red-200 dark:ring-red-500/40",
  running: "bg-blue-100 text-blue-800 ring-blue-600/20 dark:bg-blue-400/10 dark:text-blue-300 dark:ring-blue-400/30",
  pending: "bg-ink-100 text-ink-700 ring-ink-300 dark:bg-white/5 dark:text-ink-300 dark:ring-white/15",
};

export const OUTCOME_STYLES = {
  success: "text-green-700 dark:text-green-400",
  retry: "text-amber-700 dark:text-amber-400",
  error: "text-red-700 dark:text-red-400",
  stopped: "text-red-700 dark:text-red-400",
};

export const ROLE_STYLES = {
  triage: {
    icon: Search,
    badge: "bg-violet-100 text-violet-800 dark:bg-violet-400/10 dark:text-violet-300",
    border: "border-violet-400 dark:border-violet-500",
    dot: "bg-violet-500 text-white",
  },
  developer: {
    icon: Wrench,
    badge: "bg-blue-100 text-blue-800 dark:bg-blue-400/10 dark:text-blue-300",
    border: "border-blue-400 dark:border-blue-500",
    dot: "bg-blue-500 text-white",
  },
  reviewer: {
    icon: Eye,
    badge: "bg-orange-100 text-orange-800 dark:bg-orange-400/10 dark:text-orange-300",
    border: "border-orange-400 dark:border-orange-500",
    dot: "bg-orange-500 text-white",
  },
};
ROLE_STYLES.coder = ROLE_STYLES.developer;

export const TOOL_ICONS = {
  list_files: FolderOpen,
  read_file: FileText,
  propose_patch: Code,
  run_tests: Play,
  submit_triage: CheckCircle,
  submit_verdict: CheckCircle,
};

export const btn =
  "inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-forge-500";
export const btnGhost = `${btn} border border-ink-200 bg-white text-ink-700 hover:bg-ink-100 dark:border-white/10 dark:bg-white/5 dark:text-ink-200 dark:hover:bg-white/10`;
