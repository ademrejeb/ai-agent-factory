"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { useToast } from "@/components/providers/ToastProvider";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { InlineError, LoadingBlock } from "@/components/ui/States";
import { api, errorMessage } from "@/lib/api";
import { useApi } from "@/hooks/useApi";
import type { Agent, ListResponse, ProviderConnection, Workspace } from "@/lib/types";

export default function NewAgentPage() {
  const router = useRouter();
  const toast = useToast();
  const workspaces = useApi<ListResponse<Workspace>>("/api/v1/workspaces");
  const connections = useApi<ListResponse<ProviderConnection>>("/api/v1/provider-connections");

  const [workspaceId, setWorkspaceId] = useState("");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [templateName, setTemplateName] = useState("Ticketing dispatcher");
  const [templateConnectionId, setTemplateConnectionId] = useState("");
  const [ticketingBaseUrl, setTicketingBaseUrl] = useState("http://localhost:3000");
  const [ticketingAgentKey, setTicketingAgentKey] = useState("");
  const [templateBusy, setTemplateBusy] = useState(false);
  const [templateError, setTemplateError] = useState<string | null>(null);

  useEffect(() => {
    if (!workspaceId && workspaces.data?.items.length) {
      setWorkspaceId(workspaces.data.items[0].id);
    }
  }, [workspaces.data, workspaceId]);

  const langchainConnections = (connections.data?.items ?? []).filter(
    (connection) => connection.provider === "langchain",
  );

  useEffect(() => {
    if (!templateConnectionId && langchainConnections.length) {
      setTemplateConnectionId(langchainConnections[0].id);
    }
  }, [langchainConnections, templateConnectionId]);

  const canSubmit = workspaceId !== "" && name.trim().length > 0 && !busy;

  async function createDispatchTemplate(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!workspaceId || !templateConnectionId || !ticketingAgentKey.trim()) return;
    setTemplateBusy(true);
    setTemplateError(null);
    try {
      const agent = await api.post<Agent>("/api/v1/agents/from-template", {
        workspace_id: workspaceId,
        name: templateName.trim(),
        template: "ticketing_dispatch",
        provider_connection_id: templateConnectionId,
        ticketing_base_url: ticketingBaseUrl.trim(),
        ticketing_agent_key: ticketingAgentKey.trim(),
      });
      toast.push("Dispatch agent created. Run a test, then publish it.", "success");
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      setTemplateError(errorMessage(err));
      setTemplateBusy(false);
    }
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const agent = await api.post<Agent>("/api/v1/agents", {
        workspace_id: workspaceId,
        name: name.trim(),
        purpose: purpose.trim(),
        description: description.trim(),
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean)
          .slice(0, 20),
      });
      toast.push("Agent created. Next: link a model connection.", "success");
      router.push(`/agents/${agent.id}`);
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Catalog"
        title="New agent"
        description="Create the platform-owned agent record. Provider resources are linked in the next step."
        actions={
          <Link href="/agents" className="btn btn-secondary btn-md">
            <Icon name="arrow-left" size={15} />
            <span>Back to agents</span>
          </Link>
        }
      />

      <div className="grid-main">
        <Card title="Agent details">
          {workspaces.error ? <InlineError message={workspaces.error} /> : null}
          {workspaces.loading && !workspaces.data ? (
            <LoadingBlock rows={4} />
          ) : (
            <form className="stack" onSubmit={onSubmit} noValidate>
              {error ? <InlineError message={error} /> : null}
              <Field
                label="Name"
                htmlFor="agent-name"
                hint="Shown in the catalog and run explorer."
                required
              >
                <Input
                  id="agent-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Customer support assistant"
                  maxLength={200}
                  required
                  autoFocus
                />
              </Field>
              <div className="form-grid">
                <Field
                  label="Workspace"
                  htmlFor="agent-workspace"
                  hint="Separate experiments from production agents."
                  required
                >
                  <Select
                    id="agent-workspace"
                    value={workspaceId}
                    onChange={(event) => setWorkspaceId(event.target.value)}
                    required
                  >
                    <option value="">Select a workspace…</option>
                    {(workspaces.data?.items ?? []).map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name} ({workspace.kind})
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Tags"
                  htmlFor="agent-tags"
                  hint="Comma separated, up to 20."
                >
                  <Input
                    id="agent-tags"
                    value={tags}
                    onChange={(event) => setTags(event.target.value)}
                    placeholder="support, billing"
                  />
                </Field>
              </div>
              <Field
                label="Purpose"
                htmlFor="agent-purpose"
                hint="What this agent is responsible for. Useful when the catalog grows."
              >
                <Textarea
                  id="agent-purpose"
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value)}
                  placeholder="Answer account and billing questions using the internal knowledge base."
                  maxLength={4000}
                />
              </Field>
              <Field label="Description" htmlFor="agent-description">
                <Textarea
                  id="agent-description"
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Implementation notes, escalation path, or ownership."
                  maxLength={4000}
                />
              </Field>
              <div className="row">
                <Button type="submit" loading={busy} disabled={!canSubmit}>
                  Create agent
                </Button>
                <Link href="/agents" className="btn btn-ghost btn-md">
                  Cancel
                </Link>
              </div>
            </form>
          )}
        </Card>

        <div className="stack">
          <Card title="Start from the ticketing template">
            <p className="small muted" style={{ marginTop: 0 }}>
              Creates a real platform graph that loads live dispatch metrics from the
              ticketing app, asks your model to choose one technician, guards the JSON
              shape, and returns a decision the dispatcher can apply or reject safely.
            </p>
            {connections.error ? <InlineError message={connections.error} /> : null}
            {templateError ? <InlineError message={templateError} /> : null}
            {langchainConnections.length === 0 ? (
              <p className="small muted">
                Add a model connection in{" "}
                <Link href="/providers">Model providers</Link> first, or use local Ollama. The
                template needs an OpenAI-compatible model endpoint.
              </p>
            ) : (
              <form className="stack" onSubmit={createDispatchTemplate}>
                <Field label="Agent name" htmlFor="template-name" required>
                  <Input
                    id="template-name"
                    value={templateName}
                    onChange={(event) => setTemplateName(event.target.value)}
                    maxLength={200}
                    required
                  />
                </Field>
                <Field label="Model connection" htmlFor="template-connection" required>
                  <Select
                    id="template-connection"
                    value={templateConnectionId}
                    onChange={(event) => setTemplateConnectionId(event.target.value)}
                    required
                  >
                    {langchainConnections.map((connection) => (
                      <option key={connection.id} value={connection.id}>
                        {connection.name} · {String(connection.extra_config.model ?? "model")}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Ticketing base URL"
                  htmlFor="ticketing-url"
                  hint="Reachable from the API container, e.g. http://ticketing:3000."
                  required
                >
                  <Input
                    id="ticketing-url"
                    value={ticketingBaseUrl}
                    onChange={(event) => setTicketingBaseUrl(event.target.value)}
                    placeholder="http://localhost:3000"
                    required
                  />
                </Field>
                <Field
                  label="Agent context secret"
                  htmlFor="ticketing-key"
                  hint="Must equal AGENT_CONTEXT_SECRET in the ticketing app."
                  required
                >
                  <Input
                    id="ticketing-key"
                    type="password"
                    value={ticketingAgentKey}
                    onChange={(event) => setTicketingAgentKey(event.target.value)}
                    autoComplete="new-password"
                    required
                  />
                </Field>
                <Button
                  type="submit"
                  loading={templateBusy}
                  disabled={!workspaceId || !templateConnectionId || !ticketingAgentKey.trim()}
                >
                  Create dispatch agent
                </Button>
              </form>
            )}
          </Card>

          <Card title="What happens next">
            <ol className="stack-sm small muted" style={{ paddingLeft: 16, listStyle: "decimal" }}>
              <li>Connect a model endpoint (or local Ollama) in Model providers.</li>
              <li>
                On the agent page, link the model connection. The platform verifies GET /models
                before saving the association.
              </li>
              <li>
                Open the graph editor to attach tools, MCP servers, skills, and guardrails, then
                run the saved draft.
              </li>
              <li>Publish to snapshot the graph into an immutable version and a deployment record.</li>
              <li>
                Create an API key and call the gateway. Every run, tool call, and guardrail result
                is recorded.
              </li>
            </ol>
          </Card>
          <div className="panel">
            <p className="panel-title">One runtime, honest capabilities</p>
            <p className="panel-text">
              The platform runs the graph itself through LangGraph and a real model endpoint. It
              does not pretend to configure Dify or Sim, which is why those screens are gone.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
