import { Component } from "react";
import { AlertTriangle } from "lucide-react";

/** Last line of defence: a render error in one view must not blank the whole app. */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto mt-10 flex max-w-xl items-start gap-3 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-950 dark:text-red-200">
        <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <div>
          <p className="font-semibold">Something went wrong rendering this page.</p>
          <p className="mt-1 break-words">{String(this.state.error.message ?? this.state.error)}</p>
          <button className="mt-3 underline" onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      </div>
    );
  }
}
