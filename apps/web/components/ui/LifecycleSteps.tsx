import { titleCase } from "@/lib/format";

const STEPS = ["draft", "configured", "tested", "validated", "published", "monitored"];

export function LifecycleSteps({ status }: { status: string }) {
  if (status === "failed" || status === "deactivated") {
    return (
      <div className={`lifecycle lifecycle-error lifecycle-${status}`}>
        <span className="lifecycle-state">{titleCase(status)}</span>
        <span className="lifecycle-note">
          {status === "failed"
            ? "Investigate the latest run before continuing."
            : "Archived agents cannot be executed through the gateway."}
        </span>
      </div>
    );
  }

  const current = Math.max(0, STEPS.indexOf(status));
  return (
    <ol className="lifecycle" aria-label="Agent lifecycle">
      {STEPS.map((step, index) => {
        const state = index < current ? "done" : index === current ? "current" : "todo";
        return (
          <li key={step} className={`lifecycle-step lifecycle-${state}`}>
            <span className="lifecycle-dot" aria-hidden="true">
              {index < current ? "✓" : index + 1}
            </span>
            <span className="lifecycle-label">{titleCase(step)}</span>
          </li>
        );
      })}
    </ol>
  );
}
