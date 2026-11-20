"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Badge, StatusBadge } from "@/components/ui/Badge";
import { CopyButton } from "@/components/ui/CodeBlock";
import { Card } from "@/components/ui/Card";
import { Icon } from "@/components/ui/Icon";
import { ReferenceChip } from "@/components/ui/ReferenceChip";
import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import {
  formatBytes,
  formatDateTime,
  formatDuration,
  formatNumber,
  jsonPreview,
} from "@/lib/format";
import type { Run } from "@/lib/types";

export default function RunDetailPage() {
  const params = useParams<{ id: string }>();
  const runId = params?.id ?? "";
  const { data: run, loading, error, reload } = useApi<Run>(runId ? `/api/v1/runs/${runId}` : null);

  if (error) {
    return (
      <div className="stack">
        <Link href="/runs" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }}>
          <Icon name="arrow-left" size={14} />
          <span>Back to runs</span>
        </Link>
        <ErrorBlock message={error} onRetry={reload} />
      </div>
    );
  }

  if (loading && !run) return <LoadingBlock rows={7} />;
  if (!run) {
    return (
      <EmptyState
        title="Run not found"
        description="The run does not exist or belongs to another organization."
        action={
          <Link href="/runs" className="btn btn-secondary btn-sm">
            Back to runs
          </Link>
        }
      />
    );
  }

  const providerExtension = run.output?.provider_extension;
  const message = run.output?.message;

  return (
    <div className="stack-lg">
      <div>
        <Link href="/runs" className="btn btn-ghost btn-sm" style={{ marginBottom: 8 }}>
          <Icon name="arrow-left" size={14} />
          <span>Runs</span>
        </Link>
        <div className="agent-title">
          <h1 className="mono" style={{ fontSize: 20 }}>
            {run.run_id}
          </h1>
          <StatusBadge status={run.status} />
          <Badge tone={run.source === "gateway" ? "info" : "neutral"}>{run.source}</Badge>
        </div>
        <div className="agent-meta">
          <Link href={`/agents/${run.agent_id}`}>{run.agent_name ?? run.agent_id}</Link>
          <span aria-hidden="true">·</span>
          <span>{run.provider ?? "unknown provider"}</span>
          <span aria-hidden="true">·</span>
          <span>started {formatDateTime(run.started_at)}</span>
        </div>
      </div>

      <div className="grid-main">
        <div className="stack">
          {run.status === "failed" ? (
            <Card title="Failure detail">
              <div className="panel" style={{ borderColor: "rgba(248,113,113,0.35)" }}>
                {run.error_category ? (
                  <ReferenceChip code={run.error_category} message={run.error_message} />
                ) : (
                  <p className="panel-title text-danger">The run failed</p>
                )}
                <p className="panel-text">
                  {run.error_message ?? "No error message was recorded."}
                </p>
              </div>
              <p className="small faint" style={{ marginTop: 10 }}>
                Codes that look like <span className="mono">E30</span> are references from the
                connected business system. Platform codes are listed with a plain-language cause and
                fix on the chip above; the provider extension below shows the failing step.
              </p>
            </Card>
          ) : null}

          <Card
            title="Output"
            description="Bounded output preview captured by the gateway."
            actions={
              message !== undefined && message !== null ? (
                <CopyButton
                  value={typeof message === "string" ? message : JSON.stringify(message, null, 2)}
                  label="Copy message"
                />
              ) : null
            }
          >
            {message !== undefined && message !== null ? (
              <pre className="test-output">
                {typeof message === "string" ? message : jsonPreview(message)}
              </pre>
            ) : (
              <EmptyState
                compact
                icon="terminal"
                title="No normalized message"
                description="The provider returned no message field, or the run failed before producing output."
              />
            )}
            {run.output?.preview ? (
              <>
                <div className="divider" />
                <p className="small faint" style={{ marginBottom: 6 }}>
                  Stored output summary ({formatBytes(run.output.bytes)}
                  {run.output.truncated ? ", truncated" : ""})
                </p>
                <pre className="test-output">{run.output.preview}</pre>
              </>
            ) : null}
          </Card>

          <Card title="Input" description="The payload sent to the provider adapter.">
            {run.input?.preview ? (
              <pre className="test-output">{run.input.preview}</pre>
            ) : (
              <p className="small faint">No input preview recorded.</p>
            )}
            {run.input?.truncated ? (
              <p className="small faint" style={{ marginTop: 8 }}>
                Preview truncated at the retention limit. Full input was not stored.
              </p>
            ) : null}
          </Card>

          {providerExtension && Object.keys(providerExtension).length > 0 ? (
            <Card
              title="Provider extension"
              description="Provider-specific metadata passed through for diagnostics."
            >
              <pre className="test-output">{jsonPreview(providerExtension, 12000)}</pre>
            </Card>
          ) : null}
        </div>

        <div className="stack">
          <Card title="Execution">
            <dl className="kv">
              <dt>Status</dt>
              <dd>
                <StatusBadge status={run.status} />
              </dd>
              <dt>Source</dt>
              <dd>{run.source}</dd>
              <dt>Provider</dt>
              <dd>{run.provider ?? "—"}</dd>
              <dt>Provider run id</dt>
              <dd className="mono">{run.provider_run_id ?? "—"}</dd>
              <dt>Deployment</dt>
              <dd className="mono">{run.deployment_id ?? "Not gateway-attributed"}</dd>
              <dt>Duration</dt>
              <dd>{formatDuration(run.duration_ms)}</dd>
              <dt>Tokens</dt>
              <dd>
                {formatNumber(run.token_count)}{" "}
                <span className="faint small">
                  {run.token_count === null
                    ? ""
                    : run.token_count_is_estimate
                      ? "(estimated)"
                      : "(reported)"}
                </span>
              </dd>
              <dt>Started</dt>
              <dd>{formatDateTime(run.started_at)}</dd>
              <dt>Completed</dt>
              <dd>{formatDateTime(run.completed_at)}</dd>
            </dl>
          </Card>

          <Card title="Correlation">
            <p className="small muted" style={{ marginBottom: 8 }}>
              Match this value with structured logs and the <span className="mono">X-Request-ID</span>{" "}
              header returned to the caller.
            </p>
            <div className="panel mono small" style={{ overflowWrap: "anywhere" }}>
              {run.correlation_id}
            </div>
            <div className="row" style={{ marginTop: 10 }}>
              <CopyButton value={run.correlation_id} label="Copy correlation id" />
            </div>
          </Card>

          <Card title="Related">
            <div className="stack-sm">
              <Link href={`/agents/${run.agent_id}`} className="btn btn-secondary btn-sm">
                <Icon name="bot" size={14} />
                <span>Open agent</span>
              </Link>
              <Link href={`/runs?agent_id=${run.agent_id}`} className="btn btn-ghost btn-sm">
                <Icon name="play" size={14} />
                <span>All runs for this agent</span>
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
