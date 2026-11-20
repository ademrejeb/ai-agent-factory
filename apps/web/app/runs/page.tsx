"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, formatDuration, formatNumber, shortId } from "@/lib/format";
import type { Agent, ListResponse, RunPage } from "@/lib/types";

const LIMIT = 25;

const STATUSES = ["", "completed", "failed", "running", "queued", "cancelled"];
const SOURCES = ["", "test", "gateway"];
const PROVIDERS = ["", "langchain"];

function titleCase(value: string): string {
  return value ? `${value.slice(0, 1).toUpperCase()}${value.slice(1)}` : "All";
}

export default function RunsPage() {
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [provider, setProvider] = useState("");
  const [agentId, setAgentId] = useState("");
  const [offset, setOffset] = useState(0);

  const agentsApi = useApi<ListResponse<Agent>>("/api/v1/agents");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const nextStatus = params.get("status");
    const nextSource = params.get("source");
    const nextProvider = params.get("provider");
    const nextAgent = params.get("agent_id");
    if (nextStatus) setStatus(nextStatus);
    if (nextSource) setSource(nextSource);
    if (nextProvider) setProvider(nextProvider);
    if (nextAgent) setAgentId(nextAgent);
  }, []);

  const path = useMemo(() => {
    const query = new URLSearchParams();
    query.set("limit", String(LIMIT));
    query.set("offset", String(offset));
    if (status) query.set("status", status);
    if (source) query.set("source", source);
    if (provider) query.set("provider", provider);
    if (agentId) query.set("agent_id", agentId);
    return `/api/v1/runs?${query.toString()}`;
  }, [status, source, provider, agentId, offset]);

  const runs = useApi<RunPage>(path);
  const items = runs.data?.items ?? [];
  const total = runs.data?.total ?? 0;
  const hasFilters = Boolean(status || source || provider || agentId);

  function resetFilters() {
    setStatus("");
    setSource("");
    setProvider("");
    setAgentId("");
    setOffset(0);
  }

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Observability"
        title="Runs"
        description="Every test and customer-gateway execution recorded by the platform, with provider timing and safe diagnostics."
        actions={
          <Button
            variant="secondary"
            icon={<Icon name="refresh" size={15} />}
            onClick={runs.reload}
            loading={runs.loading}
          >
            Refresh
          </Button>
        }
      />

      <section className="card">
        <div className="toolbar">
          <select
            className="select"
            value={status}
            aria-label="Filter by status"
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            {STATUSES.map((value) => (
              <option key={value} value={value}>
                {value ? titleCase(value) : "All statuses"}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={source}
            aria-label="Filter by source"
            onChange={(event) => {
              setSource(event.target.value);
              setOffset(0);
            }}
          >
            {SOURCES.map((value) => (
              <option key={value} value={value}>
                {value ? titleCase(value) : "All sources"}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={provider}
            aria-label="Filter by provider"
            onChange={(event) => {
              setProvider(event.target.value);
              setOffset(0);
            }}
          >
            {PROVIDERS.map((value) => (
              <option key={value} value={value}>
                {value ? titleCase(value) : "All providers"}
              </option>
            ))}
          </select>
          <select
            className="select"
            value={agentId}
            aria-label="Filter by agent"
            onChange={(event) => {
              setAgentId(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All agents</option>
            {(agentsApi.data?.items ?? []).map((agent) => (
              <option key={agent.id} value={agent.id}>
                {agent.name}
              </option>
            ))}
          </select>
          {hasFilters ? (
            <Button variant="ghost" size="sm" onClick={resetFilters}>
              Clear
            </Button>
          ) : null}
          <span className="toolbar-spacer" />
          <span className="small muted">
            {formatNumber(total)} {total === 1 ? "run" : "runs"}
          </span>
        </div>

        {runs.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={runs.error} onRetry={runs.reload} />
          </div>
        ) : runs.loading && !runs.data ? (
          <LoadingBlock rows={6} />
        ) : items.length === 0 ? (
          <EmptyState
            icon="play"
            title={hasFilters ? "No runs match these filters" : "No runs recorded yet"}
            description={
              hasFilters
                ? "Widen the filters to see more executions."
                : "Test a linked agent or call the gateway with a customer API key."
            }
            action={
              hasFilters ? (
                <Button variant="secondary" size="sm" onClick={resetFilters}>
                  Clear filters
                </Button>
              ) : (
                <Link href="/agents" className="btn btn-primary btn-sm">
                  Open agents
                </Link>
              )
            }
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Agent</th>
                    <th>Status</th>
                    <th>Provider</th>
                    <th>Source</th>
                    <th>Duration</th>
                    <th>Tokens</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((run) => (
                    <tr key={run.run_id}>
                      <td className="cell-mono">
                        <Link href={`/runs/${run.run_id}`}>{shortId(run.run_id)}</Link>
                      </td>
                      <td>
                        <Link href={`/agents/${run.agent_id}`}>
                          {run.agent_name ?? shortId(run.agent_id)}
                        </Link>
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="muted">{run.provider ?? "—"}</td>
                      <td className="muted">{run.source}</td>
                      <td className="cell-mono">{formatDuration(run.duration_ms)}</td>
                      <td className="cell-mono">
                        {formatNumber(run.token_count)}
                        {run.token_count_is_estimate ? (
                          <span className="faint" title="Estimated by the platform">
                            {" "}
                            est.
                          </span>
                        ) : null}
                      </td>
                      <td className="muted nowrap">{formatDateTime(run.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pagination">
              <span>
                Showing {offset + 1}–{Math.min(offset + LIMIT, total)} of {formatNumber(total)}
              </span>
              <div className="pagination-actions">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={offset + LIMIT >= total}
                  onClick={() => setOffset(offset + LIMIT)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}
      </section>

      <p className="small faint">
        Input and output are stored as bounded previews. Full prompts and documents are not retained
        by default.
      </p>
    </div>
  );
}
