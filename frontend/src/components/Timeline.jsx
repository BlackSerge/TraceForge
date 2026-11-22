import { AlertTriangle, CheckCircle, Code, XCircle } from "lucide-react";
import { OUTCOME_STYLES, ROLE_STYLES, TOOL_ICONS } from "../styles";
import { RoleBadge } from "./ui";

export function Diff({ text }) {
  return (
    <pre className="overflow-x-auto rounded-lg border border-ink-200 bg-white py-2 font-mono text-xs leading-5 dark:border-white/10 dark:bg-ink-900">
      {text.split("\n").map((line, i) => {
        let cls = "text-ink-700 dark:text-ink-300";
        if (line.startsWith("+") && !line.startsWith("+++"))
          cls = "bg-green-50 text-green-900 dark:bg-green-950 dark:text-green-200";
        else if (line.startsWith("-") && !line.startsWith("---"))
          cls = "bg-red-50 text-red-900 dark:bg-red-950 dark:text-red-200";
        else if (line.startsWith("@@")) cls = "bg-forge-50 text-forge-700 dark:bg-forge-500/10 dark:text-forge-100";
        else if (line.startsWith("+++") || line.startsWith("---")) cls = "text-ink-500";
        return (
          <span key={i} className={`block px-3 whitespace-pre ${cls}`}>
            {line || " "}
          </span>
        );
      })}
    </pre>
  );
}

export function CodeBlock({ children, label }) {
  return (
    <details className="group">
      <summary className="cursor-pointer text-xs text-ink-500 transition-colors select-none hover:text-ink-700 dark:hover:text-ink-200">
        {label}
      </summary>
      <pre className="max-h-64 overflow-auto rounded-md bg-ink-100 p-3 font-mono text-xs leading-5 whitespace-pre-wrap text-ink-700 dark:bg-ink-950 dark:text-ink-300">
        {children}
      </pre>
    </details>
  );
}

export function ToolCall({ call }) {
  const { name, args = {}, result = {} } = call;
  const Icon = result.error ? AlertTriangle : (TOOL_ICONS[name] ?? Code);
  const argText = Object.entries(args)
    .filter(([k]) => k !== "reasoning" && k !== "new_content")
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  return (
    <div className="mt-2 space-y-2">
      <div className="flex items-center gap-2 font-mono text-xs text-ink-700 dark:text-ink-200">
        <Icon
          className={`size-4 shrink-0 ${result.error ? "text-red-600 dark:text-red-400" : "text-ink-500"}`}
          aria-hidden="true"
        />
        <code className="break-all">
          {name}({argText})
        </code>
      </div>
      {result.error && <p className="text-sm text-red-700 dark:text-red-400">{result.error}</p>}
      {name === "read_file" && result.content !== undefined && <CodeBlock label="Show file content">{result.content}</CodeBlock>}
      {name === "propose_patch" && result.diff !== undefined && <Diff text={result.diff} />}
      {name === "run_tests" && result.passed !== undefined && (
        <>
          <p
            className={`inline-flex items-center gap-1 text-sm font-medium ${result.passed ? "text-green-700 dark:text-green-400" : "text-red-700 dark:text-red-400"}`}
          >
            {result.passed ? <CheckCircle className="size-4" /> : <XCircle className="size-4" />}
            tests {result.passed ? "passed" : "failed"}
          </p>
          <CodeBlock label="Show test output">{result.output}</CodeBlock>
        </>
      )}
    </div>
  );
}

export function Timeline({ steps }) {
  return (
    <ol className="space-y-4">
      {steps.map((step) => {
        const style = ROLE_STYLES[step.agent_role] ?? ROLE_STYLES.developer;
        const Icon = style.icon;
        return (
          <li key={step.id} className="relative flex gap-3">
            <span className={`mt-1 grid size-7 shrink-0 place-items-center rounded-full ${style.dot}`}>
              <Icon className="size-4" aria-hidden="true" />
            </span>
            <div
              className={`min-w-0 flex-1 rounded-lg border-l-4 border-y border-r border-y-ink-200 border-r-ink-200 bg-white p-3 transition-colors dark:border-y-white/10 dark:border-r-white/10 dark:bg-ink-900 ${style.border}`}
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <strong className="text-sm">Step {step.step_id}</strong>
                <RoleBadge role={step.agent_role} />
                <span className={`text-xs font-medium ${OUTCOME_STYLES[step.outcome] ?? ""}`}>{step.outcome}</span>
                <span className="font-mono text-xs text-ink-500">
                  {step.latency_ms ?? "?"} ms · {step.tokens_in ?? "?"}→{step.tokens_out ?? "?"} tokens ·{" "}
                  {step.model ?? "?"}
                </span>
              </div>
              {step.reasoning_summary && (
                <p className="mt-2 text-sm text-ink-700 italic dark:text-ink-300">{step.reasoning_summary}</p>
              )}
              {step.tool_calls.map((call, i) => (
                <ToolCall key={i} call={call} />
              ))}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
