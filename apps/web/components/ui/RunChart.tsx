import type { OverviewDay } from "@/lib/types";

export function RunChart({ days }: { days: OverviewDay[] }) {
  const totals = days.map((day) => day.completed + day.failed + day.other);
  const max = Math.max(1, ...totals);
  const hasData = totals.some((total) => total > 0);
  const labelEvery = days.length > 14 ? Math.ceil(days.length / 7) : 1;

  return (
    <div className="chart">
      <div className="chart-legend">
        <span>
          <i className="legend-dot legend-completed" /> Completed
        </span>
        <span>
          <i className="legend-dot legend-failed" /> Failed
        </span>
        <span>
          <i className="legend-dot legend-other" /> In progress
        </span>
        <span className="chart-max">peak {max}/day</span>
      </div>
      <div className="chart-plot" role="img" aria-label="Runs per day">
        {!hasData ? <div className="chart-empty">No runs in this window yet.</div> : null}
        {days.map((day, index) => {
          const total = day.completed + day.failed + day.other;
          return (
            <div className="chart-column" key={day.date}>
              <div className="chart-bar-track">
                <div
                  className="chart-bar"
                  style={{ height: `${Math.max(total === 0 ? 0 : 3, (total / max) * 100)}%` }}
                  title={`${day.date}: ${day.completed} completed, ${day.failed} failed, ${day.other} other`}
                >
                  {day.other > 0 ? (
                    <span
                      className="chart-segment chart-segment-other"
                      style={{ flex: day.other }}
                    />
                  ) : null}
                  {day.failed > 0 ? (
                    <span
                      className="chart-segment chart-segment-failed"
                      style={{ flex: day.failed }}
                    />
                  ) : null}
                  {day.completed > 0 ? (
                    <span
                      className="chart-segment chart-segment-completed"
                      style={{ flex: day.completed }}
                    />
                  ) : null}
                </div>
              </div>
              <span className="chart-label">
                {index % labelEvery === 0 || index === days.length - 1
                  ? day.date.slice(5)
                  : ""}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
