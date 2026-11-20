"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { RunChart } from "@/components/ui/RunChart";
import { StatCard } from "@/components/ui/StatCard";
import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import {
  formatDateTime,
  formatDuration,
  formatNumber,
  formatPercent,
  providerConsoleUrl,
} from "@/lib/format";
import type { Overview } from "@/lib/types";

const RANGES = [7, 14, 30, 90];

export default function OverviewPage() {
  const [days, setDays] = useState(7);
  const { data, loading, error, reload } = useApi<Overview>(`/api/v1/overview?days=${days}`);

  const counts = data?.counts;
  const rangeLabel = useMemo(() => `Last ${days} days`, [days]);

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Control plane"
        title="Overview"
        description="What your agents actually did. Every number below comes from a recorded run, a saved agent, or a real endpoint check — nothing is estimated for effect."
        actions={
          <>
            <label className="sr-only" htmlFor="overview-range">
              Time window
            </label>
            <select
              id="overview-range"
              className="select select-inline"
              value={days}
              onChange={(event) => setDays(Number(event.target.value))}
            >
              {RANGES.map((range) => (
                <option key={range} value={range}>
                  Last {range} days
                </option>
              ))}
            </select>
            <Button
              variant="secondary"
              icon={<Icon name="refresh" size={15} />}
              onClick={reload}
              loading={loading}
            >
              Refresh
            </Button>
            <Link href="/agents/new" className="btn btn-primary btn-md">
              <Icon name="plus" size={15} />
              <span>New agent</span>
            </Link>
          </>
        }
      />

      {error ? <ErrorBlock message={error} onRetry={reload} /> : null}

      {counts ? (
        <Link href="/agents/new" className="template-banner">
          <div>
            <strong>Ticketing dispatcher template</strong>
            <span>
              Create an agent that reads live technician metrics and recommends the best worker.
            </span>
          </div>
          <span className="template-cta">Open template →</span>
        </Link>
      ) : null}

      {counts && counts.agents_total === 0 ? (
        <section className="onboarding-panel">
          <div>
            <span className="page-eyebrow">First run</span>
            <h2>Turn one model endpoint into a callable agent.</h2>
            <p>
              Connect a local Ollama model or any OpenAI-compatible endpoint, start from the
              ticketing dispatcher, test it against the real model, then publish. The only numbers
              you will see are the ones your runs produce.
            </p>
            <div className="onboarding-actions">
              <Link href="/providers" className="btn btn-secondary btn-md">
                <Icon name="plug" size={15} />
                <span>Connect a provider</span>
              </Link>
              <Link href="/agents/new" className="btn btn-primary btn-md">
                <Icon name="plus" size={15} />
                <span>Create an agent</span>
              </Link>
            </div>
          </div>
          <ol className="onboarding-steps">
            <li>
              <span>1</span>
              Connect Ollama locally or any OpenAI-compatible endpoint. The platform verifies it
              through GET /models and shows the models it really found.
            </li>
            <li>
              <span>2</span>
              Use the ticketing template or build a graph from scratch.
            </li>
            <li>
              <span>3</span>
              Test, publish, issue an API key, and call the gateway from another app.
            </li>
          </ol>
        </section>
      ) : null}

      {loading && !data ? (
        <div className="grid-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div className="stat" key={index}>
              <LoadingBlock rows={2} />
            </div>
          ))}
        </div>
      ) : counts ? (
        <div className="grid-4">
          <StatCard
            label="Published agents"
            value={formatNumber(counts.agents_published)}
            detail={`${formatNumber(counts.agents_total)} active agents in total`}
            icon={<Icon name="bot" size={16} />}
          />
          <StatCard
            label="Runs in this window"
            value={formatNumber(counts.runs_total)}
            detail={
              counts.runs_total === 0
                ? "No one has run an agent in this window"
                : `${formatNumber(counts.runs_completed)} finished well, ${formatNumber(counts.runs_failed)} failed`
            }
            icon={<Icon name="play" size={16} />}
            tone={counts.runs_failed > 0 ? "danger" : "default"}
          />
          <StatCard
            label="Finished without an error"
            value={formatPercent(counts.success_rate)}
            detail={
              counts.success_rate === null
                ? "Nothing has run yet, so there is no rate to show"
                : `${formatNumber(counts.runs_completed)} of ${formatNumber(counts.runs_total)} completed runs succeeded`
            }
            icon={<Icon name="check" size={16} />}
            tone={
              counts.success_rate === null
                ? "default"
                : counts.success_rate >= 0.95
                  ? "success"
                  : counts.success_rate >= 0.8
                    ? "warning"
                    : "danger"
            }
          />
          <StatCard
            label="Slow runs (95th percentile)"
            value={formatDuration(counts.p95_latency_ms)}
            detail={
              counts.p50_latency_ms === null
                ? "No completed run has a duration yet"
                : `Half finish in ${formatDuration(counts.p50_latency_ms)}; this is the slow tail`
            }
            icon={<Icon name="clock" size={16} />}
          />
        </div>
      ) : null}

      <div className="grid-main">
        <Card
          title="Run volume"
          description="Each bar is a day of real executions. Completed runs are green, failures are red, and queued/cancelled runs are grey."
          padded
        >
          {loading && !data ? (
            <LoadingBlock rows={5} />
          ) : data ? (
            <RunChart days={data.runs_by_day} />
          ) : null}
          <div className="divider" />
          <div className="row-wrap small muted">
            <span>
              Tokens reported by providers: <strong>{formatNumber(counts?.tokens_reported)}</strong>
            </span>
            <span aria-hidden="true">·</span>
            <span>
              estimated: <strong>{formatNumber(counts?.tokens_estimated)}</strong>
            </span>
            <span aria-hidden="true">·</span>
            <span>
              connections up: <strong>{formatNumber(counts?.provider_connected)}</strong>/
              {formatNumber(counts?.provider_connections)}
            </span>
          </div>
        </Card>

        <Card
          title="Needs attention"
          description="Derived from agent sync errors and unhealthy deployments."
          actions={
            data && data.attention.length > 0 ? (
              <Badge tone="warning">{data.attention.length}</Badge>
            ) : null
          }
          padded={false}
        >
          {loading && !data ? (
            <LoadingBlock rows={3} />
          ) : !data || data.attention.length === 0 ? (
            <EmptyState
              compact
              icon="check"
              title="Nothing flagged"
              description="No sync errors or unhealthy deployments are recorded for this organization."
            />
          ) : (
            <ul className="list-plain">
              {data.attention.map((item) => (
                <li className="list-item" key={item.agent_id}>
                  <div>
                    <Link className="list-item-title" href={`/agents/${item.agent_id}`}>
                      {item.name}
                    </Link>
                    <p className="attention-reason">{item.reason}</p>
                  </div>
                  <StatusBadge status={item.lifecycle_status} />
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid-main">
        <Card
          title="Recent runs"
          description="The latest executions across tests and the customer gateway."
          actions={
            <Link href="/runs" className="btn btn-ghost btn-sm">
              Run explorer
              <Icon name="chevron-right" size={14} />
            </Link>
          }
          padded={false}
        >
          {loading && !data ? (
            <LoadingBlock rows={5} />
          ) : !data || data.recent_runs.length === 0 ? (
            <EmptyState
              compact
              icon="play"
              title="No runs yet"
              description="Test a linked agent or call it with a customer API key to populate this view."
              action={
                <Link href="/agents" className="btn btn-secondary btn-sm">
                  Open agents
                </Link>
              }
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Source</th>
                    <th>Duration</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_runs.map((run) => (
                    <tr key={run.run_id}>
                      <td className="cell-mono">
                        <Link href={`/runs/${run.run_id}`}>{run.run_id.slice(0, 14)}…</Link>
                      </td>
                      <td>
                        <Link href={`/agents/${run.agent_id}`}>
                          {run.agent_name ?? run.agent_id.slice(0, 12)}
                        </Link>
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="muted">{run.source}</td>
                      <td className="cell-mono">{formatDuration(run.duration_ms)}</td>
                      <td className="muted nowrap">{formatDateTime(run.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="stack">
          <Card title="Provider connections" padded={false}>
            {loading && !data ? (
              <LoadingBlock rows={3} />
            ) : !data || data.provider_connections.length === 0 ? (
              <EmptyState
                compact
                icon="plug"
                title="No provider connected"
                description="Connect a model endpoint before linking an agent. Local Ollama is the fastest path."
                action={
                  <Link href="/providers" className="btn btn-primary btn-sm">
                    Connect provider
                  </Link>
                }
              />
            ) : (
              <ul className="list-plain">
                {data.provider_connections.map((conn) => (
                  <li className="list-item" key={conn.id}>
                    <div>
                      <p className="list-item-title">{conn.name}</p>
                      <p className="list-item-meta">
                        {conn.provider} · {conn.base_url}
                      </p>
                      <p className="list-item-meta">
                        checked {formatDateTime(conn.last_checked_at)}
                      </p>
                    </div>
                    <div className="stack-sm" style={{ alignItems: "flex-end" }}>
                      <StatusBadge status={conn.status} />
                      <a
                        className="small"
                        href={providerConsoleUrl(conn.base_url)}
                        target="_blank"
                        rel="noreferrer"
                      >
                        Open console
                      </a>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Most used agents" padded={false}>
            {loading && !data ? (
              <LoadingBlock rows={3} />
            ) : !data || data.top_agents.length === 0 ? (
              <EmptyState
                compact
                icon="bot"
                title="No usage in this window"
                description="Agent run counts appear once executions are recorded."
              />
            ) : (
              <ul className="list-plain">
                {data.top_agents.map((agent) => (
                  <li className="list-item" key={agent.agent_id}>
                    <div>
                      <Link className="list-item-title" href={`/agents/${agent.agent_id}`}>
                        {agent.name}
                      </Link>
                      <p className="list-item-meta">
                        {formatNumber(agent.runs)} runs · {formatNumber(agent.failed)} failed
                      </p>
                    </div>
                    <span className="mono small muted">{formatNumber(agent.runs)}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      {data && data.recent_failures.length > 0 ? (
        <Card
          title="Recent failures"
          description="Provider and platform errors recorded during execution."
          actions={
            <Link href="/runs?status=failed" className="btn btn-ghost btn-sm">
              Filter failures
              <Icon name="chevron-right" size={14} />
            </Link>
          }
          padded={false}
        >
          <ul className="list-plain">
            {data.recent_failures.map((run) => (
              <li className="list-item" key={run.run_id}>
                <div>
                  <Link className="list-item-title" href={`/runs/${run.run_id}`}>
                    {run.agent_name ?? run.agent_id}
                  </Link>
                  <p className="list-item-meta">
                    {run.error_category ?? "error"} · {run.error_message ?? "No message recorded"}
                  </p>
                </div>
                <span className="muted small nowrap">{formatDateTime(run.started_at)}</span>
              </li>
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}
