import Link from "next/link";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CodeBlock } from "@/components/ui/CodeBlock";
import { PageHeader } from "@/components/ui/PageHeader";

const runExample = `curl -X POST "$API_BASE/api/v1/agents/agent_123/runs" \\
  -H "Authorization: Bearer aaf_..." \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: order-42" \\
  -d '{
    "input": { "message": "How do I reset my password?" },
    "conversation_id": null,
    "metadata": { "source": "customer-portal" }
  }'`;

const responseExample = `{
  "run_id": "run_9f2...",
  "agent_id": "agent_123",
  "agent_name": "Support assistant",
  "deployment_id": "dep_7c1...",
  "status": "completed",
  "source": "gateway",
  "provider": "langchain",
  "provider_run_id": null,
  "correlation_id": "6a1f...",
  "input": { "bytes": 51, "preview": "{\\"message\\": \\"How do I reset my password?\\"}", "truncated": false },
  "output": {
    "message": "Follow the password reset instructions…",
    "conversation_id": "conv_9",
    "bytes": 240,
    "preview": "…"
  },
  "error_category": null,
  "error_message": null,
  "duration_ms": 812,
  "token_count": 214,
  "token_count_is_estimate": false,
  "started_at": "2026-10-27T10:15:22+00:00",
  "completed_at": "2026-10-27T10:15:23+00:00"
}`;

const errorExample = `{
  "error": {
    "code": "invalid_lifecycle",
    "message": "Agent is not eligible for this kind of execution.",
    "details": { "status": "configured", "source": "gateway" }
  }
}`;

export default function DocsPage() {
  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Reference"
        title="API reference"
        description="The platform contract for operating agents and executing them from customer applications. Provider APIs stay behind the adapters."
        actions={
          <Link href="/credentials" className="btn btn-secondary btn-md">
            Manage API keys
          </Link>
        }
      />

      <Card title="Base URL and conventions">
        <div className="grid-2">
          <div className="stack-sm">
            <p className="small muted">
              All endpoints below are versioned under <span className="mono">/api/v1</span> and
              accept and return JSON.
            </p>
            <dl className="kv">
              <dt>Control plane</dt>
              <dd className="mono">$API_BASE/api/v1</dd>
              <dt>Local API</dt>
              <dd className="mono">http://localhost:8080</dd>
              <dt>Web proxy</dt>
              <dd className="mono">/backend-api/*</dd>
            </dl>
          </div>
          <div className="panel">
            <p className="panel-title">Error envelope</p>
            <p className="panel-text">
              Every handled error uses the same object. Validation failures return HTTP 422 with a{" "}
              <span className="mono">details.fields</span> array.
            </p>
          </div>
        </div>
        <div className="divider" />
        <CodeBlock code={errorExample} language="json" />
      </Card>

      <Card title="Authentication">
        <div className="grid-2">
          <div className="stack-sm">
            <p className="panel-title">Operator session</p>
            <p className="panel-text">
              Email/password login sets the httpOnly <span className="mono">factory_session</span>{" "}
              cookie. The browser talks to the Next.js proxy so the cookie remains first-party.
            </p>
            <div className="row-wrap">
              <Badge tone="info">POST /api/v1/auth/login</Badge>
              <Badge tone="info">POST /api/v1/auth/register</Badge>
              <Badge tone="info">POST /api/v1/auth/logout</Badge>
              <Badge tone="info">GET /api/v1/auth/me</Badge>
            </div>
          </div>
          <div className="stack-sm">
            <p className="panel-title">Customer credential</p>
            <p className="panel-text">
              Send <span className="mono">Authorization: Bearer aaf_…</span>. Only the SHA-256 hash is
              stored. Keys carry scopes; <span className="mono">agents:run</span> is required for
              execution.
            </p>
            <div className="row-wrap">
              <Badge tone="accent">GET /api/v1/credentials</Badge>
              <Badge tone="accent">POST /api/v1/credentials</Badge>
              <Badge tone="accent">POST /api/v1/credentials/{"{id}"}/revoke</Badge>
            </div>
          </div>
        </div>
      </Card>

      <Card
        title="Execution gateway"
        description="The only surface customer applications need. The provider is resolved from the agent's active deployment."
      >
        <div className="stack">
          <CodeBlock code={runExample} language="bash" />
          <div className="row-wrap small muted">
            <Badge tone="success">POST</Badge>
            <span className="mono">/api/v1/agents/{"{agent_id}"}/runs</span>
            <span>· idempotent with</span>
            <span className="mono">Idempotency-Key</span>
            <span>· rate limited per credential</span>
          </div>
          <CodeBlock code={responseExample} language="json" />
          <p className="small faint">
            Streaming and async runs use separate routes:{" "}
            <span className="mono">/api/v1/agents/{"{agent_id}"}/runs/stream</span> (SSE) and{" "}
            <span className="mono">/api/v1/agents/{"{agent_id}"}/runs/async</span> (reserved; the
            platform runtime has no external queue and returns{" "}
            <span className="mono">unsupported_capability</span>). The blocking route waits until the
            graph returns or the configured timeout elapses. A stream client that disconnects has its
            run finalized as <span className="mono">cancelled</span>, with usage and audit rows. Poll{" "}
            <span className="mono">GET /api/v1/runs/{"{run_id}"}</span> for recorded state.
          </p>
        </div>
      </Card>

      <Card title="Endpoint summary" padded={false}>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Method</th>
                <th>Path</th>
                <th>Auth</th>
                <th>Behaviour</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/health</td>
                <td>public</td>
                <td>Process liveness.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/ready</td>
                <td>public</td>
                <td>Database reachability check.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/providers</td>
                <td>public</td>
                <td>Verified provider catalog and limitations.</td>
              </tr>
              <tr>
                <td className="mono">GET/POST</td>
                <td className="mono">/api/v1/provider-connections</td>
                <td>session</td>
                <td>List safe metadata or create and verify a connection.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/provider-connections/{"{id}"}/check</td>
                <td>session</td>
                <td>Re-run the provider connectivity check.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/provider-connections/{"{id}"}/resources</td>
                <td>session</td>
                <td>List linkable resources for the connection.</td>
              </tr>
              <tr>
                <td className="mono">GET/POST</td>
                <td className="mono">/api/v1/workspaces</td>
                <td>session</td>
                <td>List workspaces; creation requires owner or admin.</td>
              </tr>
              <tr>
                <td className="mono">GET/POST</td>
                <td className="mono">/api/v1/agents</td>
                <td>session</td>
                <td>Catalog of logical agents.</td>
              </tr>
              <tr>
                <td className="mono">GET/PATCH</td>
                <td className="mono">/api/v1/agents/{"{id}"}</td>
                <td>session</td>
                <td>Read or update platform-owned metadata.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/link</td>
                <td>session</td>
                <td>Verify GET /models and link the model connection.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/test</td>
                <td>session</td>
                <td>Blocking test execution recorded as a run.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/test/stream</td>
                <td>session</td>
                <td>SSE test execution: chunk, status, final, and error events.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/test/async</td>
                <td>session</td>
                <td>Reserved for queued execution; the platform runtime returns unsupported_capability.</td>
              </tr>
              <tr>
                <td className="mono">GET/PUT</td>
                <td className="mono">/api/v1/agents/{"{id}"}/graph</td>
                <td>session</td>
                <td>Read or replace the platform-owned LangGraph draft.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/graph/dry_run</td>
                <td>session</td>
                <td>Execute the saved draft through the real runtime.</td>
              </tr>
              <tr>
                <td className="mono">GET/POST</td>
                <td className="mono">/api/v1/tools</td>
                <td>session</td>
                <td>Reusable HTTP and MCP tools, with encrypted headers.</td>
              </tr>
              <tr>
                <td className="mono">GET/POST</td>
                <td className="mono">/api/v1/skills</td>
                <td>session</td>
                <td>Reusable instruction blocks attached to agents.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/publish</td>
                <td>session</td>
                <td>Create an immutable version and deployment record.</td>
              </tr>
              <tr>
                <td className="mono">POST</td>
                <td className="mono">/api/v1/agents/{"{id}"}/deactivate</td>
                <td>session</td>
                <td>Archive the agent and deactivate its deployment.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/agents/{"{id}"}/runs</td>
                <td>session</td>
                <td>Recent runs for one agent.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/runs</td>
                <td>session</td>
                <td>Filter by status, provider, source, agent, and time window.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/runs/{"{run_id}"}</td>
                <td>session or key</td>
                <td>Run detail, scoped to the caller&apos;s organization.</td>
              </tr>
              <tr>
                <td className="mono">GET</td>
                <td className="mono">/api/v1/overview</td>
                <td>session</td>
                <td>Aggregated metrics from persisted runs.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Lifecycle semantics">
        <div className="grid-2">
          <div className="panel">
            <p className="panel-title">Transitions that gate execution</p>
            <p className="panel-text">
              A test requires a linked resource. A successful test moves the agent to validated. The
              gateway accepts only published or monitored agents with an active deployment. A failed
              gateway run marks the deployment unhealthy.
            </p>
          </div>
          <div className="panel">
            <p className="panel-title">What publish does</p>
            <p className="panel-text">
              Publishing checks the model endpoint and snapshots the saved graph into an immutable
              version that the gateway executes. Later draft edits do not change live traffic until
              the next publish. A failed gateway run marks the deployment unhealthy.
            </p>
          </div>
        </div>
      </Card>

      <Card title="Runtime constraints">
        <ul className="stack-sm small muted" style={{ paddingLeft: 16, listStyle: "disc" }}>
          <li>
            One execution engine: the platform-owned LangGraph runtime against an
            OpenAI-compatible endpoint. Dify and Sim were removed because their APIs could not be
            configured end to end here.
          </li>
          <li>
            Graphs are acyclic and cannot merge branches. Agent nodes add a bounded tool-calling
            loop; plain LLM nodes stay single-shot.
          </li>
          <li>
            Tools are organization-owned HTTP or MCP endpoints. Headers are encrypted at rest;
            values may reference <span className="mono">{"{{secrets.NAME}}"}</span>.
          </li>
          <li>
            Guardrails inspect a rendered value and route pass/fail. Both branches must end at an
            output so blocked answers remain visible.
          </li>
          <li>
            There is no external queue. Blocking and streaming runs are real; async returns{" "}
            <span className="mono">unsupported_capability</span>.
          </li>
        </ul>
      </Card>
    </div>
  );
}
