"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useToast } from "@/components/providers/ToastProvider";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { CopyButton } from "@/components/ui/CodeBlock";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { LifecycleSteps } from "@/components/ui/LifecycleSteps";
import { Tabs } from "@/components/ui/Tabs";
import {
  EmptyState,
  ErrorBlock,
  InlineError,
  LoadingBlock,
} from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage, streamRequest, type StreamEventPayload } from "@/lib/api";
import {
  capabilityLabel,
  capabilityValue,
  formatDateTime,
  formatDuration,
  formatNumber,
  jsonPreview,
  providerConsoleUrl,
  shortId,
} from "@/lib/format";
import type {
  Agent,
  AgentSecret,
  AgentVersion,
  Deployment,
  ListResponse,
  ProviderConnection,
  ProviderDescriptor,
  Run,
  Skill,
  Workspace,
} from "@/lib/types";

const DEPLOYABLE = new Set(["validated", "published", "monitored"]);
const TERMINAL_RUN_STATUSES = new Set(["completed", "failed", "cancelled"]);

type TestMode = "blocking" | "stream" | "async";

function capabilityEnabled(value: unknown): boolean {
  return value === true || value === "verified" || value === "platform_owned";
}

export default function AgentDetailPage() {
  const params = useParams<{ id: string }>();
  const agentId = params?.id ?? "";
  const toast = useToast();

  const agentApi = useApi<Agent>(agentId ? `/api/v1/agents/${agentId}` : null);
  const workspacesApi = useApi<ListResponse<Workspace>>("/api/v1/workspaces");
  const connectionsApi = useApi<ListResponse<ProviderConnection>>("/api/v1/provider-connections");
  const providersApi = useApi<ListResponse<ProviderDescriptor>>("/api/v1/providers");
  const runsApi = useApi<ListResponse<Run>>(agentId ? `/api/v1/agents/${agentId}/runs?limit=25` : null);
  const versionsApi = useApi<ListResponse<AgentVersion>>(
    agentId ? `/api/v1/agents/${agentId}/versions` : null,
  );
  const deploymentsApi = useApi<ListResponse<Deployment>>(
    agentId ? `/api/v1/agents/${agentId}/deployments` : null,
  );
  const secretsApi = useApi<ListResponse<AgentSecret>>(
    agentId ? `/api/v1/agents/${agentId}/secrets` : null,
  );

  const agent = agentApi.data;

  const [tab, setTab] = useState("runs");
  const [name, setName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [skillIds, setSkillIds] = useState<string[]>([]);
  const [workspaceId, setWorkspaceId] = useState("");
  const skillsApi = useApi<ListResponse<Skill>>("/api/v1/skills");
  const [saveBusy, setSaveBusy] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const [connectionId, setConnectionId] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  const [testInput, setTestInput] = useState('{\n  "message": "Hello"\n}');
  const [testMode, setTestMode] = useState<TestMode>("blocking");
  const [testBusy, setTestBusy] = useState(false);
  const [testError, setTestError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Run | null>(null);

  const [streamText, setStreamText] = useState("");
  const [streamStatus, setStreamStatus] = useState<string | null>(null);
  const [streamEventCount, setStreamEventCount] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const [asyncRun, setAsyncRun] = useState<Run | null>(null);

  const [secretName, setSecretName] = useState("ticketing_agent_key");
  const [secretValue, setSecretValue] = useState("");
  const [secretBusy, setSecretBusy] = useState(false);
  const [secretError, setSecretError] = useState<string | null>(null);

  const [actionBusy, setActionBusy] = useState<"publish" | "deactivate" | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  const reloadAll = useCallback(() => {
    agentApi.reload();
    runsApi.reload();
    versionsApi.reload();
    deploymentsApi.reload();
    connectionsApi.reload();
  }, [agentApi, runsApi, versionsApi, deploymentsApi, connectionsApi]);

  const reloadRef = useRef(reloadAll);
  useEffect(() => {
    reloadRef.current = reloadAll;
  });

  useEffect(() => {
    if (!agent) return;
    setName(agent.name);
    setPurpose(agent.purpose);
    setDescription(agent.description);
    setTags(agent.tags.join(", "));
    setSkillIds(agent.skill_ids ?? []);
    setWorkspaceId(agent.workspace_id);
  }, [agent]);

  useEffect(() => {
    if (agent?.provider_connection_id) setConnectionId(agent.provider_connection_id);
  }, [agent?.provider_connection_id]);

  const selectedConnection = useMemo(
    () => connectionsApi.data?.items.find((conn) => conn.id === connectionId) ?? null,
    [connectionsApi.data, connectionId],
  );

  const selectedProvider = useMemo(
    () => providersApi.data?.items.find((item) => item.id === selectedConnection?.provider) ?? null,
    [providersApi.data, selectedConnection],
  );

  const agentProvider = useMemo(
    () => providersApi.data?.items.find((item) => item.id === agent?.provider) ?? null,
    [providersApi.data, agent?.provider],
  );

  const linkedConnection = useMemo(
    () => connectionsApi.data?.items.find((conn) => conn.id === agent?.provider_connection_id) ?? null,
    [connectionsApi.data, agent?.provider_connection_id],
  );

  const connectionCapabilities = linkedConnection?.capabilities ?? {};
  const supportsBlocking =
    connectionCapabilities.blocking === undefined
      ? true
      : capabilityEnabled(connectionCapabilities.blocking);
  const supportsStreaming = capabilityEnabled(connectionCapabilities.streaming);
  const supportsAsync = capabilityEnabled(connectionCapabilities.async);

  useEffect(() => {
    const available: TestMode[] = [];
    if (supportsStreaming) available.push("stream");
    if (supportsAsync) available.push("async");
    if (supportsBlocking) available.push("blocking");
    if (available.length > 0 && !available.includes(testMode)) {
      setTestMode(available[0]);
    }
  }, [supportsBlocking, supportsStreaming, supportsAsync, testMode]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  useEffect(() => {
    const runId = asyncRun?.run_id;
    if (!runId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;

    const tick = async () => {
      try {
        const fresh = await api.get<Run>(`/api/v1/runs/${runId}`);
        if (!active) return;
        setAsyncRun(fresh);
        if (!TERMINAL_RUN_STATUSES.has(fresh.status) && attempts < 150) {
          attempts += 1;
          timer = setTimeout(tick, 2000);
        } else {
          reloadRef.current();
        }
      } catch (error) {
        if (!active) return;
        setTestError(errorMessage(error));
        if (attempts < 5) {
          attempts += 1;
          timer = setTimeout(tick, 3000);
        }
      }
    };

    timer = setTimeout(tick, 1500);
    return () => {
      active = false;
      if (timer !== null) clearTimeout(timer);
    };
  }, [asyncRun?.run_id]);

  async function saveMetadata(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    setSaveBusy(true);
    setSaveError(null);
    try {
      await api.patch<Agent>(`/api/v1/agents/${agent.id}`, {
        name: name.trim(),
        purpose,
        description,
        workspace_id: workspaceId,
        tags: tags
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean)
          .slice(0, 20),
        skill_ids: skillIds,
      });
      toast.push("Agent settings saved.", "success");
      reloadAll();
    } catch (error) {
      setSaveError(errorMessage(error));
    } finally {
      setSaveBusy(false);
    }
  }

  async function saveSecret(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent || !secretName.trim() || !secretValue) return;
    setSecretBusy(true);
    setSecretError(null);
    try {
      await api.put(`/api/v1/agents/${agent.id}/secrets/${encodeURIComponent(secretName.trim())}`, {
        value: secretValue,
      });
      setSecretValue("");
      secretsApi.reload();
      toast.push("Secret saved. HTTP nodes can reference it as {{secrets.NAME}}.", "success");
    } catch (error) {
      setSecretError(errorMessage(error));
    } finally {
      setSecretBusy(false);
    }
  }

  async function deleteSecret(name: string) {
    if (!agent) return;
    setSecretBusy(true);
    setSecretError(null);
    try {
      await api.del(`/api/v1/agents/${agent.id}/secrets/${encodeURIComponent(name)}`);
      secretsApi.reload();
      toast.push("Secret removed.", "success");
    } catch (error) {
      setSecretError(errorMessage(error));
    } finally {
      setSecretBusy(false);
    }
  }

  async function linkProvider(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent || !connectionId) return;
    setLinkBusy(true);
    setLinkError(null);
    try {
      await api.post<Agent>(`/api/v1/agents/${agent.id}/link`, {
        provider_connection_id: connectionId,
      });
      toast.push("Model connection linked and verified.", "success");
      reloadAll();
    } catch (error) {
      setLinkError(errorMessage(error));
    } finally {
      setLinkBusy(false);
    }
  }

  async function runTest(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!agent) return;
    const parsed = parseTestInput();
    if (!parsed) return;
    setTestBusy(true);
    setTestError(null);
    setTestResult(null);
    try {
      const run = await api.post<Run>(`/api/v1/agents/${agent.id}/test`, { input: parsed });
      setTestResult(run);
      if (run.status === "completed") {
        toast.push("Test completed and recorded.", "success");
      } else {
        toast.push("Provider reported a failed run. Inspect the error.", "error");
      }
      reloadAll();
    } catch (error) {
      setTestError(errorMessage(error));
      reloadAll();
    } finally {
      setTestBusy(false);
    }
  }

  function parseTestInput(): Record<string, unknown> | null {
    let parsed: unknown;
    try {
      parsed = JSON.parse(testInput);
    } catch {
      setTestError("Input must be valid JSON.");
      return null;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setTestError('Input must be a JSON object, for example {"message": "Hello"}.');
      return null;
    }
    return parsed as Record<string, unknown>;
  }

  async function runStreamTest() {
    if (!agent) return;
    const parsed = parseTestInput();
    if (!parsed) return;

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setTestBusy(true);
    setTestError(null);
    setTestResult(null);
    setStreamText("");
    setStreamStatus("starting");
    setStreamEventCount(0);

    let finalOutcome: { runId: string | null; status: string | null } = {
      runId: null,
      status: null,
    };
    try {
      await streamRequest(
        `/api/v1/agents/${agent.id}/test/stream`,
        { input: parsed },
        {
          signal: controller.signal,
          onEvent: (event) => {
            setStreamEventCount((count) => count + 1);
            if (event.type === "chunk" && event.text) {
              setStreamText((current) => current + event.text);
            }
            if (event.type === "status") {
              const status = event.data.status;
              if (typeof status === "string") setStreamStatus(status);
            }
            if (event.type === "final") {
              finalOutcome = {
                ...finalOutcome,
                status:
                  typeof event.data.status === "string" ? event.data.status : "completed",
              };
              setStreamStatus(finalOutcome.status);
              if (typeof event.data.run_id === "string") {
                finalOutcome = { ...finalOutcome, runId: event.data.run_id };
              }
            }
            if (event.type === "error") {
              finalOutcome = {
                ...finalOutcome,
                status: "failed",
              };
              setStreamStatus("failed");
              if (typeof event.data.run_id === "string") {
                finalOutcome = { ...finalOutcome, runId: event.data.run_id };
              }
              setTestError(
                typeof event.data.error_message === "string"
                  ? event.data.error_message
                  : "The provider stream failed.",
              );
            }
          },
        },
      );
      if (finalOutcome.runId) {
        try {
          const run = await api.get<Run>(`/api/v1/runs/${finalOutcome.runId}`);
          setTestResult(run);
        } catch {
          // The stream result is still visible even if the run read fails.
        }
      }
      if (finalOutcome.status === "completed") {
        toast.push("Stream completed and the run was recorded.", "success");
      } else if (finalOutcome.status === "failed") {
        toast.push("The provider stream failed. Inspect the run for details.", "error");
      }
      reloadAll();
    } catch (error) {
      if (controller.signal.aborted) {
        toast.push("Stream cancelled. The run is marked cancelled.", "info");
      } else {
        setTestError(errorMessage(error));
      }
      if (finalOutcome.runId) {
        try {
          const run = await api.get<Run>(`/api/v1/runs/${finalOutcome.runId}`);
          setTestResult(run);
        } catch {
          // Ignore; the error above is the useful message.
        }
      }
      reloadAll();
    } finally {
      setTestBusy(false);
      if (abortRef.current === controller) abortRef.current = null;
    }
  }

  function cancelStream() {
    abortRef.current?.abort();
  }

  function runCurrent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (testMode === "stream") {
      void runStreamTest();
      return;
    }
    if (testMode === "async") {
      void runAsyncTest();
      return;
    }
    void runTest(event);
  }

  async function runAsyncTest() {
    if (!agent) return;
    const parsed = parseTestInput();
    if (!parsed) return;
    setTestBusy(true);
    setTestError(null);
    setAsyncRun(null);
    try {
      const run = await api.post<Run>(`/api/v1/agents/${agent.id}/test/async`, {
        input: parsed,
      });
      setAsyncRun(run);
      toast.push("Run queued with the provider. Polling for the terminal result.", "info");
      reloadAll();
    } catch (error) {
      setTestError(errorMessage(error));
      reloadAll();
    } finally {
      setTestBusy(false);
    }
  }

  async function publish() {
    if (!agent) return;
    setActionBusy("publish");
    setActionError(null);
    try {
      await api.post<Agent>(`/api/v1/agents/${agent.id}/publish`);
      toast.push("Published. A version and deployment record were created.", "success");
      reloadAll();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setActionBusy(null);
    }
  }

  async function deactivate() {
    if (!agent) return;
    setActionBusy("deactivate");
    setActionError(null);
    try {
      await api.post<Agent>(`/api/v1/agents/${agent.id}/deactivate`);
      toast.push("Agent deactivated and archived.", "success");
      setConfirmDeactivate(false);
      reloadAll();
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setActionBusy(null);
    }
  }

  if (agentApi.error) {
    return (
      <div className="stack">
        <Link href="/agents" className="btn btn-ghost btn-sm" style={{ alignSelf: "flex-start" }}>
          <Icon name="arrow-left" size={14} />
          <span>Back to agents</span>
        </Link>
        <ErrorBlock message={agentApi.error} onRetry={agentApi.reload} />
      </div>
    );
  }

  if (agentApi.loading && !agent) return <LoadingBlock rows={6} />;
  if (!agent) return <EmptyState title="Agent not found" description="This agent does not exist." />;

  const canPublish = DEPLOYABLE.has(agent.lifecycle_status);
  const canDeactivate = agent.lifecycle_status !== "deactivated";
  const consoleUrl = linkedConnection ? providerConsoleUrl(linkedConnection.base_url) : null;
  const latestRun = testResult ?? runsApi.data?.items[0] ?? null;
  const testModes: Array<{ id: TestMode; label: string; enabled: boolean; hint: string }> = [
    {
      id: "blocking",
      label: "Blocking",
      enabled: supportsBlocking,
      hint: "One HTTP call. The response arrives after the provider finishes.",
    },
    {
      id: "stream",
      label: "Streaming",
      enabled: supportsStreaming,
      hint: "Server-Sent Events. Text appears as the provider generates it.",
    },
    {
      id: "async",
      label: "Async",
      enabled: supportsAsync,
      hint: "Queue the run with the provider and poll until it reaches a terminal state.",
    },
  ];
  const activeTestMode = testModes.find((mode) => mode.id === testMode) ?? testModes[0];

  function runPanel(run: Run) {
    return (
      <>
        <div className="row-between" style={{ marginBottom: 8 }}>
          <div className="row-wrap">
            <StatusBadge status={run.status} />
            <span className="small muted">
              {run.source === "test" ? "test" : "gateway"} · {formatDuration(run.duration_ms)}
            </span>
            <span className="small faint">
              tokens {formatNumber(run.token_count)}
              {run.token_count_is_estimate ? " (estimate)" : " (reported)"}
            </span>
          </div>
          <Link href={`/runs/${run.run_id}`} className="small">
            Inspect run
          </Link>
        </div>
        {run.status === "failed" || run.status === "cancelled" ? (
          <div
            className="panel"
            style={{
              borderColor:
                run.status === "cancelled"
                  ? "rgba(251,191,36,0.35)"
                  : "rgba(248,113,113,0.35)",
            }}
          >
            <p
              className={`panel-title ${
                run.status === "cancelled" ? "text-warning" : "text-danger"
              }`}
            >
              {run.error_category ??
                (run.status === "cancelled" ? "Cancelled" : "Provider failure")}
            </p>
            <p className="panel-text">{run.error_message ?? "No message recorded."}</p>
          </div>
        ) : (
          <pre className="test-output">
            {typeof run.output?.message === "string"
              ? run.output.message
              : jsonPreview(run.output)}
          </pre>
        )}
      </>
    );
  }

  return (
    <div className="stack-lg">
      <div className="agent-title-row">
        <div>
          <Link href="/agents" className="btn btn-ghost btn-sm" style={{ marginBottom: 8 }}>
            <Icon name="arrow-left" size={14} />
            <span>Agents</span>
          </Link>
          <div className="agent-title">
            <h1>{agent.name}</h1>
            <StatusBadge status={agent.lifecycle_status} />
            {agent.archived_at ? <Badge tone="neutral">Archived</Badge> : null}
          </div>
          <div className="agent-meta">
            <span className="mono">{shortId(agent.id)}</span>
            {agent.provider ? (
              <>
                <span aria-hidden="true">·</span>
                <span className="mono">
                  {agent.provider}
                  {agent.provider_resource_kind ? `/${agent.provider_resource_kind}` : ""}
                </span>
              </>
            ) : (
              <>
                <span aria-hidden="true">·</span>
                <span>No provider linked</span>
              </>
            )}
            <span aria-hidden="true">·</span>
            <span>Created {formatDateTime(agent.created_at)}</span>
          </div>
        </div>
        <div className="page-actions">
          <Button
            variant="secondary"
            icon={<Icon name="refresh" size={15} />}
            onClick={reloadAll}
          >
            Refresh
          </Button>
          {agent.provider ? (
            <Link
              href={`/agents/${agent.id}/graph`}
              className="btn btn-secondary btn-md"
              title="Open the platform-owned graph editor"
            >
              <Icon name="workflow" size={15} />
              <span>Graph editor</span>
            </Link>
          ) : null}
          <Button
            onClick={publish}
            loading={actionBusy === "publish"}
            disabled={!canPublish || Boolean(agent.archived_at)}
            title={
              canPublish
                ? "Create a version and platform deployment record"
                : "Publish requires a successful test first"
            }
            icon={<Icon name="arrow-up-right" size={15} />}
          >
            Publish
          </Button>
          {consoleUrl ? (
            <a className="btn btn-secondary btn-md" href={consoleUrl} target="_blank" rel="noreferrer">
              <Icon name="terminal" size={15} />
              <span>Open endpoint</span>
            </a>
          ) : null}
        </div>
      </div>

      {agent.last_sync_error ? <InlineError message={agent.last_sync_error} /> : null}
      {actionError ? <InlineError message={actionError} /> : null}

      <Card title="Lifecycle" description="Draft → configured → tested → validated → published → monitored.">
        <LifecycleSteps status={agent.lifecycle_status} />
        <div className="divider" />
        <div className="row-wrap small muted">
          <span>
            Publishing snapshots the saved graph into an immutable version and creates a platform
            deployment record. Tests and draft runs use the saved draft; live traffic uses the
            published snapshot.
          </span>
        </div>
        {agent.provider ? (
          <>
            <div className="divider" />
            <div className="row-wrap small muted">
              <span>
                <Link href={`/agents/${agent.id}/graph`}>Open the graph editor</Link> to change the
                draft, attach tools, skills, and guardrails, and run it against the linked model.
              </span>
            </div>
          </>
        ) : null}
      </Card>

      <div className="agent-detail-grid">
        <div className="stack">
          <Card title="Configuration" description="Platform-owned metadata. The model endpoint is configured in Model providers.">
            <form className="stack" onSubmit={saveMetadata} noValidate>
              {saveError ? <InlineError message={saveError} /> : null}
              <div className="form-grid">
                <Field label="Name" htmlFor="edit-name" required>
                  <Input
                    id="edit-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    maxLength={200}
                    required
                  />
                </Field>
                <Field label="Workspace" htmlFor="edit-workspace">
                  <Select
                    id="edit-workspace"
                    value={workspaceId}
                    onChange={(event) => setWorkspaceId(event.target.value)}
                  >
                    {(workspacesApi.data?.items ?? []).map((workspace) => (
                      <option key={workspace.id} value={workspace.id}>
                        {workspace.name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="Tags" htmlFor="edit-tags" hint="Comma separated.">
                  <Input
                    id="edit-tags"
                    value={tags}
                    onChange={(event) => setTags(event.target.value)}
                  />
                </Field>
                <div className="span-2">
                  <span className="field-label">Skills applied to every agent node</span>
                  {(skillsApi.data?.items.length ?? 0) === 0 ? (
                    <p className="small faint">
                      No skills yet. <Link href="/skills">Create one</Link> to share rules across
                      agents.
                    </p>
                  ) : (
                    <div className="graph-check-list">
                      {(skillsApi.data?.items ?? []).map((skill) => (
                        <label className="checkbox-row" key={skill.id}>
                          <input
                            type="checkbox"
                            checked={skillIds.includes(skill.id)}
                            onChange={(event) =>
                              setSkillIds((current) =>
                                event.target.checked
                                  ? [...current, skill.id]
                                  : current.filter((id) => id !== skill.id),
                              )
                            }
                          />
                          <span>
                            <strong>{skill.name}</strong>{" "}
                            <span className="small faint">{skill.description}</span>
                          </span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
                <Field label="Purpose" htmlFor="edit-purpose">
                  <Input
                    id="edit-purpose"
                    value={purpose}
                    onChange={(event) => setPurpose(event.target.value)}
                    maxLength={4000}
                  />
                </Field>
                <div className="span-2">
                  <Field label="Description" htmlFor="edit-description">
                    <Textarea
                      id="edit-description"
                      value={description}
                      onChange={(event) => setDescription(event.target.value)}
                      maxLength={4000}
                    />
                  </Field>
                </div>
              </div>
              <div className="row">
                <Button type="submit" loading={saveBusy} disabled={!name.trim()}>
                  Save changes
                </Button>
                <span className="small faint">Saved to this platform only.</span>
              </div>
            </form>
          </Card>

          <Card
            title="Model link"
            description="A logical agent references one verified OpenAI-compatible model connection. The graph is created and owned by this platform."
          >
            {connectionsApi.error ? <InlineError message={connectionsApi.error} /> : null}
            {!connectionsApi.loading && (connectionsApi.data?.items.length ?? 0) === 0 ? (
              <EmptyState
                compact
                icon="plug"
                title="No provider connections"
                description="Connect a provider first, then return here to link a resource."
                action={
                  <Link href="/providers" className="btn btn-primary btn-sm">
                    Connect provider
                  </Link>
                }
              />
            ) : (
              <form className="stack" onSubmit={linkProvider} noValidate>
                {linkError ? <InlineError message={linkError} /> : null}
                <div className="form-grid">
                  <Field
                    label="Provider connection"
                    htmlFor="link-connection"
                    hint="Only connections in this organization are selectable."
                    required
                  >
                    <Select
                      id="link-connection"
                      value={connectionId}
                      onChange={(event) => setConnectionId(event.target.value)}
                    >
                      <option value="">Select a connection…</option>
                      {(connectionsApi.data?.items ?? []).map((conn) => (
                        <option key={conn.id} value={conn.id}>
                          {conn.name} ({conn.provider} · {conn.status})
                        </option>
                      ))}
                    </Select>
                  </Field>
                </div>
                {selectedProvider ? (
                  <div className="panel">
                    <p className="panel-title">{selectedProvider.name} verified capabilities</p>
                    <div className="capability-list" style={{ marginTop: 6 }}>
                      {Object.entries(selectedProvider.capabilities).map(([key, value]) => (
                        <span className="capability-chip" key={key}>
                          <strong>{capabilityLabel(key)}:</strong> {capabilityValue(value)}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
                <div className="row">
                  <Button
                    type="submit"
                    loading={linkBusy}
                    disabled={!connectionId}
                  >
                    {agent.provider_connection_id ? "Re-link resource" : "Link and verify"}
                  </Button>
                  {agent.provider_connection_id ? (
                    <span className="small faint">Re-linking replaces the current association.</span>
                  ) : null}
                </div>
              </form>
            )}

            {agent.provider ? (
              <>
                <div className="divider" />
                <dl className="kv">
                  <dt>Platform agent</dt>
                  <dd className="mono">{agent.id}</dd>
                  <dt>Provider</dt>
                  <dd>{agent.provider}</dd>
                  <dt>{agent.provider === "langchain" ? "Graph" : "Resource id"}</dt>
                  <dd className="mono">
                    {agent.provider_resource_id ??
                      (agent.provider === "langchain"
                        ? "Platform-owned (see Graph editor)"
                        : "App-scoped key (no id required)")}
                  </dd>
                  <dt>Resource kind</dt>
                  <dd>{agent.provider_resource_kind ?? "—"}</dd>
                  <dt>Connection</dt>
                  <dd>{linkedConnection?.name ?? "—"}</dd>
                </dl>
              </>
            ) : null}
          </Card>

          <Card
            title="Test console"
            description="Execute through the platform and record a real run. Pick the transport this connection supports; each mode uses the same agent and credentials."
          >
            <form className="stack" onSubmit={runCurrent} noValidate>
              <div className="tabs test-mode-tabs" role="tablist" aria-label="Test execution mode">
                {testModes.map((mode) => (
                  <button
                    key={mode.id}
                    type="button"
                    role="tab"
                    aria-selected={testMode === mode.id}
                    className={`tab ${testMode === mode.id ? "tab-active" : ""}`}
                    disabled={!mode.enabled}
                    title={
                      mode.enabled
                        ? mode.hint
                        : `This connection does not advertise ${mode.label.toLowerCase()} execution.`
                    }
                    onClick={() => {
                      setTestMode(mode.id);
                      setTestError(null);
                    }}
                  >
                    {mode.label}
                  </button>
                ))}
              </div>
              <p className="small faint">{activeTestMode.hint}</p>

              {testError ? <InlineError message={testError} /> : null}

              <Field
                label="Input (JSON object)"
                htmlFor="test-input"
                hint="The object is passed as the graph input. Required fields declared on the input node must be present."
              >
                <Textarea
                  id="test-input"
                  className="textarea-mono"
                  value={testInput}
                  onChange={(event) => setTestInput(event.target.value)}
                  spellCheck={false}
                  rows={6}
                />
              </Field>

              <div className="row">
                <Button
                  type="submit"
                  loading={testBusy}
                  disabled={
                    agent.lifecycle_status === "draft" ||
                    Boolean(agent.archived_at) ||
                    !activeTestMode.enabled
                  }
                  icon={<Icon name="play" size={15} />}
                >
                  {testMode === "stream"
                    ? "Start stream"
                    : testMode === "async"
                      ? "Queue run"
                      : "Run test"}
                </Button>
                {testMode === "stream" && testBusy ? (
                  <Button
                    type="button"
                    variant="secondary"
                    icon={<Icon name="close" size={15} />}
                    onClick={cancelStream}
                  >
                    Stop stream
                  </Button>
                ) : null}
                {agent.lifecycle_status === "draft" ? (
                  <span className="small faint">Link a model connection before testing.</span>
                ) : !activeTestMode.enabled ? (
                  <span className="small faint">
                    This connection does not advertise {activeTestMode.label.toLowerCase()}{" "}
                    execution.
                  </span>
                ) : null}
              </div>
            </form>

            {testMode === "blocking" && latestRun ? (
              <>
                <div className="divider" />
                {runPanel(latestRun)}
              </>
            ) : null}

            {testMode === "stream" ? (
              <>
                <div className="divider" />
                <div className="row-between" style={{ marginBottom: 8 }}>
                  <div className="row-wrap">
                    <StatusBadge status={streamStatus ?? "idle"} />
                    <span className="small faint">{streamEventCount} events</span>
                    {streamText ? (
                      <span className="small faint">{streamText.length} characters</span>
                    ) : null}
                  </div>
                  {testResult ? (
                    <Link href={`/runs/${testResult.run_id}`} className="small">
                      Inspect run
                    </Link>
                  ) : null}
                </div>
                <pre className="test-output">
                  {streamText ||
                    (testBusy
                      ? "Waiting for the first chunk…"
                      : "No streamed text yet. Some workflow modes emit only a final output.")}
                </pre>
                {testResult ? (
                  <>
                    <div className="divider" />
                    {runPanel(testResult)}
                  </>
                ) : null}
              </>
            ) : null}

            {testMode === "async" ? (
              <>
                <div className="divider" />
                {asyncRun ? (
                  <>
                    {runPanel(asyncRun)}
                    {!TERMINAL_RUN_STATUSES.has(asyncRun.status) ? (
                      <p className="small faint" style={{ marginTop: 8 }}>
                        Polling the provider every 2 seconds. The run updates in place.
                      </p>
                    ) : null}
                  </>
                ) : (
                  <p className="small faint">
                    Queueing returns immediately with a platform run id. The platform polls the
                    provider until the run reaches a terminal state.
                  </p>
                )}
              </>
            ) : null}
          </Card>
        </div>

        <div className="stack">
          <Card title="Deployment" padded>
            {agent.deployment ? (
              <div className="stack-sm">
                <div className="row-between">
                  <span className="small muted">Health</span>
                  <StatusBadge status={agent.deployment.health_status} />
                </div>
                <div className="row-between">
                  <span className="small muted">Status</span>
                  <StatusBadge status={agent.deployment.status} />
                </div>
                <div className="row-between">
                  <span className="small muted">Environment</span>
                  <span className="small">{agent.deployment.environment}</span>
                </div>
                <div className="row-between">
                  <span className="small muted">Last check</span>
                  <span className="small">{formatDateTime(agent.deployment.last_health_check_at)}</span>
                </div>
                {agent.deployment.last_error ? (
                  <div className="panel">
                    <p className="panel-title text-danger">Last error</p>
                    <p className="panel-text">{agent.deployment.last_error}</p>
                  </div>
                ) : null}
              </div>
            ) : (
              <EmptyState
                compact
                icon="layers"
                title="Not published"
                description="A deployment record is created only when you publish a validated agent."
              />
            )}
          </Card>

          <Card title="Gateway access" padded>
            <p className="panel-text" style={{ marginBottom: 10 }}>
              Customer keys call <span className="mono">POST /api/v1/agents/{"{id}"}/runs</span>.
              Only published or monitored agents with an active deployment are eligible.
            </p>
            <div className="stack-sm">
              <div className="row-between">
                <span className="small muted">Eligible</span>
                <StatusBadge
                  status={
                    agent.lifecycle_status === "published" || agent.lifecycle_status === "monitored"
                      ? "active"
                      : "inactive"
                  }
                  label={
                    agent.lifecycle_status === "published" || agent.lifecycle_status === "monitored"
                      ? "Yes"
                      : "No"
                  }
                />
              </div>
              <Link href="/credentials" className="btn btn-secondary btn-sm">
                <Icon name="key" size={14} />
                <span>Manage API keys</span>
              </Link>
            </div>
          </Card>

          <Card title="Danger zone" padded>
            <p className="panel-text" style={{ marginBottom: 10 }}>
              Deactivation archives the agent and marks the latest deployment inactive. Historical
              runs and versions are retained.
            </p>
            <Button
              variant="danger"
              size="sm"
              onClick={() => setConfirmDeactivate(true)}
              disabled={!canDeactivate}
              icon={<Icon name="trash" size={14} />}
            >
              {canDeactivate ? "Deactivate agent" : "Already deactivated"}
            </Button>
          </Card>
        </div>
      </div>

      {agent.provider === "langchain" ? (
        <Card title="Agent secrets">
          <p className="small muted" style={{ marginTop: 0 }}>
            Encrypted values available to HTTP nodes as{" "}
            <code className="mono">{"{{secrets.NAME}}"}</code>. The ticketing dispatcher
            template expects <code className="mono">ticketing_agent_key</code>.
          </p>
          {secretsApi.error ? <InlineError message={secretsApi.error} /> : null}
          {secretError ? <InlineError message={secretError} /> : null}
          <form className="stack" onSubmit={saveSecret}>
            <div className="form-grid">
              <Field label="Secret name" htmlFor="secret-name" required>
                <Input
                  id="secret-name"
                  value={secretName}
                  onChange={(event) => setSecretName(event.target.value)}
                  placeholder="ticketing_agent_key"
                  maxLength={64}
                  required
                />
              </Field>
              <Field
                label="Secret value"
                htmlFor="secret-value"
                hint="Stored encrypted; never returned by the API."
                required
              >
                <Input
                  id="secret-value"
                  type="password"
                  value={secretValue}
                  onChange={(event) => setSecretValue(event.target.value)}
                  autoComplete="new-password"
                  required
                />
              </Field>
            </div>
            <div className="row">
              <Button type="submit" loading={secretBusy} disabled={!secretValue}>
                Save secret
              </Button>
            </div>
          </form>
          <div className="stack-sm" style={{ marginTop: 14 }}>
            {(secretsApi.data?.items ?? []).map((secret) => (
              <div key={secret.name} className="row-between panel" style={{ padding: "8px 12px" }}>
                <div>
                  <span className="mono small">{secret.name}</span>
                  <span className="faint small" style={{ marginLeft: 8 }}>
                    updated {formatDateTime(secret.updated_at)}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => deleteSecret(secret.name)}
                  disabled={secretBusy}
                >
                  Delete
                </Button>
              </div>
            ))}
            {(secretsApi.data?.items.length ?? 0) === 0 ? (
              <span className="small faint">No secrets stored yet.</span>
            ) : null}
          </div>
        </Card>
      ) : null}

      <Card title="Activity" padded={false}>
        <div style={{ padding: "0 14px" }}>
          <Tabs
            active={tab}
            onChange={setTab}
            tabs={[
              { id: "runs", label: "Runs", count: runsApi.data?.items.length },
              { id: "versions", label: "Versions", count: versionsApi.data?.items.length },
              { id: "deployments", label: "Deployments", count: deploymentsApi.data?.items.length },
            ]}
          />
        </div>

        {tab === "runs" ? (
          runsApi.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={runsApi.error} onRetry={runsApi.reload} />
            </div>
          ) : runsApi.loading && !runsApi.data ? (
            <LoadingBlock rows={4} />
          ) : (runsApi.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              compact
              icon="play"
              title="No runs recorded"
              description="Run a test or call the gateway to record the first execution."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Run</th>
                    <th>Status</th>
                    <th>Source</th>
                    <th>Duration</th>
                    <th>Tokens</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {(runsApi.data?.items ?? []).map((run) => (
                    <tr key={run.run_id}>
                      <td className="cell-mono">
                        <Link href={`/runs/${run.run_id}`}>{shortId(run.run_id)}</Link>
                      </td>
                      <td>
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="muted">{run.source}</td>
                      <td className="cell-mono">{formatDuration(run.duration_ms)}</td>
                      <td className="cell-mono">{formatNumber(run.token_count)}</td>
                      <td className="muted nowrap">{formatDateTime(run.started_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}

        {tab === "versions" ? (
          versionsApi.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={versionsApi.error} onRetry={versionsApi.reload} />
            </div>
          ) : versionsApi.loading && !versionsApi.data ? (
            <LoadingBlock rows={3} />
          ) : (versionsApi.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              compact
              icon="layers"
              title="No versions"
              description="Versions are immutable snapshots created at publish time."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Provider</th>
                    <th>Resource</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {(versionsApi.data?.items ?? []).map((version) => (
                    <tr key={version.id}>
                      <td className="mono">v{version.version}</td>
                      <td className="muted">{String(version.snapshot.provider ?? "—")}</td>
                      <td className="cell-mono">
                        {String(
                          version.snapshot.provider_resource_id ??
                            version.snapshot.provider_resource_kind ??
                            "—",
                        )}
                      </td>
                      <td className="muted nowrap">{formatDateTime(version.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}

        {tab === "deployments" ? (
          deploymentsApi.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={deploymentsApi.error} onRetry={deploymentsApi.reload} />
            </div>
          ) : deploymentsApi.loading && !deploymentsApi.data ? (
            <LoadingBlock rows={3} />
          ) : (deploymentsApi.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              compact
              icon="layers"
              title="No deployments"
              description="Publish a validated agent to create the first deployment record."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Deployment</th>
                    <th>Environment</th>
                    <th>Status</th>
                    <th>Health</th>
                    <th>Last check</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {(deploymentsApi.data?.items ?? []).map((deployment) => (
                    <tr key={deployment.id}>
                      <td className="cell-mono">{shortId(deployment.id)}</td>
                      <td className="muted">{deployment.environment}</td>
                      <td>
                        <StatusBadge status={deployment.status} />
                      </td>
                      <td>
                        <StatusBadge status={deployment.health_status} />
                      </td>
                      <td className="muted nowrap">
                        {formatDateTime(deployment.last_health_check_at)}
                      </td>
                      <td className="muted nowrap">{formatDateTime(deployment.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        ) : null}
      </Card>

      {agentProvider ? (
        <p className="small faint">
          Provider-specific behaviour for <strong>{agentProvider.name}</strong>:{" "}
          {agentProvider.limitations.join(" ")}
        </p>
      ) : null}

      <div className="row">
        <CopyButton value={agent.id} label="Copy platform agent id" />
      </div>

      <ConfirmDialog
        open={confirmDeactivate}
        title="Deactivate this agent?"
        message="The agent will be archived, its latest deployment marked inactive, and gateway calls will be rejected. Runs and versions remain available."
        confirmLabel="Deactivate"
        tone="danger"
        loading={actionBusy === "deactivate"}
        onConfirm={deactivate}
        onClose={() => setConfirmDeactivate(false)}
      />
    </div>
  );
}
