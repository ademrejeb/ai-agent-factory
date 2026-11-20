"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { formatDateTime, titleCase } from "@/lib/format";
import type { Agent, ListResponse, Workspace } from "@/lib/types";

const STATUS_FILTERS = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "configured", label: "Configured" },
  { value: "validated", label: "Validated" },
  { value: "published", label: "Published" },
  { value: "monitored", label: "Monitored" },
  { value: "failed", label: "Failed" },
];

export default function AgentsPage() {
  const agentsApi = useApi<ListResponse<Agent>>("/api/v1/agents");
  const workspacesApi = useApi<ListResponse<Workspace>>("/api/v1/workspaces");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");

  const workspaceNames = useMemo(() => {
    const map = new Map<string, string>();
    for (const workspace of workspacesApi.data?.items ?? []) map.set(workspace.id, workspace.name);
    return map;
  }, [workspacesApi.data]);

  const items = useMemo(() => {
    const all = agentsApi.data?.items ?? [];
    const needle = query.trim().toLowerCase();
    return all.filter((agent) => {
      if (status && agent.lifecycle_status !== status) return false;
      if (!needle) return true;
      return (
        agent.name.toLowerCase().includes(needle) ||
        agent.description.toLowerCase().includes(needle) ||
        agent.purpose.toLowerCase().includes(needle) ||
        agent.tags.some((tag) => tag.toLowerCase().includes(needle))
      );
    });
  }, [agentsApi.data, query, status]);

  const total = agentsApi.data?.items.length ?? 0;

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Catalog"
        title="Agents"
        description="Logical agents owned by this organization. Each one runs a platform-owned graph against a real OpenAI-compatible model, with the tools, skills, and guardrails you attach."
        actions={
          <Link href="/agents/new" className="btn btn-primary btn-md">
            <Icon name="plus" size={15} />
            <span>New agent</span>
          </Link>
        }
      />

      <Link href="/agents/new" className="template-banner">
        <div>
          <strong>Start with the ticketing dispatcher</strong>
          <span>
            A real LangGraph template that turns live ticket metrics into a technician decision.
          </span>
        </div>
        <span className="template-cta">Use template →</span>
      </Link>

      <section className="card">
        <div className="toolbar">
          <div className="toolbar-search">
            <Icon name="search" size={15} />
            <input
              className="input"
              placeholder="Search name, purpose, tags…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Search agents"
            />
          </div>
          <select
            className="select"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            aria-label="Filter by lifecycle status"
          >
            {STATUS_FILTERS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <span className="toolbar-spacer" />
          <span className="small muted">
            {items.length} of {total}
          </span>
          <Button
            variant="ghost"
            size="sm"
            icon={<Icon name="refresh" size={14} />}
            onClick={agentsApi.reload}
            loading={agentsApi.loading}
          >
            Refresh
          </Button>
        </div>

        {agentsApi.error ? (
          <div style={{ padding: 16 }}>
            <ErrorBlock message={agentsApi.error} onRetry={agentsApi.reload} />
          </div>
        ) : agentsApi.loading && !agentsApi.data ? (
          <LoadingBlock rows={5} />
        ) : total === 0 ? (
          <EmptyState
            icon="bot"
            title="No agents yet"
            description="Create a logical agent, link it to a model endpoint, then build the graph. Local Ollama is a valid endpoint and so is any OpenAI-compatible gateway."
            action={
              <Link href="/agents/new" className="btn btn-primary btn-sm">
                Create the first agent
              </Link>
            }
          />
        ) : items.length === 0 ? (
          <EmptyState
            compact
            icon="search"
            title="No matching agents"
            description="Adjust the search text or lifecycle filter."
            action={
              <Button
                variant="secondary"
                size="sm"
                onClick={() => {
                  setQuery("");
                  setStatus("");
                }}
              >
                Clear filters
              </Button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Agent</th>
                  <th>Workspace</th>
                  <th>Provider</th>
                  <th>Lifecycle</th>
                  <th>Deployment</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {items.map((agent) => (
                  <tr key={agent.id}>
                    <td>
                      <Link href={`/agents/${agent.id}`}>{agent.name}</Link>
                      <div className="list-item-meta">
                        {agent.tags.length > 0
                          ? agent.tags.map((tag) => (
                              <span className="tag" key={tag} style={{ marginRight: 4 }}>
                                {tag}
                              </span>
                            ))
                          : agent.purpose || "No purpose recorded"}
                      </div>
                    </td>
                    <td className="muted">
                      {workspaceNames.get(agent.workspace_id) ?? "Unknown workspace"}
                    </td>
                    <td>
                      {agent.provider ? (
                        <span className="mono small">
                          {agent.provider}
                          {agent.provider_resource_kind ? ` · ${agent.provider_resource_kind}` : ""}
                        </span>
                      ) : (
                        <span className="faint small">Not linked</span>
                      )}
                    </td>
                    <td>
                      <StatusBadge status={agent.lifecycle_status} />
                    </td>
                    <td>
                      {agent.deployment ? (
                        <span className="row-wrap">
                          <StatusBadge status={agent.deployment.health_status} />
                          <span className="faint small">
                            {titleCase(agent.deployment.environment)}
                          </span>
                        </span>
                      ) : (
                        <span className="faint small">None</span>
                      )}
                    </td>
                    <td className="muted nowrap">{formatDateTime(agent.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
