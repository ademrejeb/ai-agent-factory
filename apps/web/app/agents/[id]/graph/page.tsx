"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useToast } from "@/components/providers/ToastProvider";
import { LocalGraphCanvas } from "@/components/graph/LocalGraphCanvas";
import { LocalGraphInspector } from "@/components/graph/LocalGraphInspector";
import { LocalGraphPalette } from "@/components/graph/LocalGraphPalette";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, formatDuration, formatNumber, jsonPreview, shortId } from "@/lib/format";
import {
  NODE_META,
  NODE_ORDER,
  createNode,
  localGraphProblem,
  runMessage,
  type LocalGraph,
  type LocalGraphDryRun,
  type LocalGraphResponse,
  type LocalGraphValidation,
  type LocalNode,
  type LocalNodeType,
} from "@/lib/local-graph";
import type { Agent } from "@/lib/types";

type GraphAction = "validate" | "save" | "run" | null;

function snapshot(graph: LocalGraph): string {
  return JSON.stringify({ nodes: graph.nodes, edges: graph.edges });
}

function nextPosition(graph: LocalGraph): { x: number; y: number } {
  const nodes = Object.values(graph.nodes);
  if (nodes.length === 0) return { x: 60, y: 160 };
  const rightmost = nodes.reduce((best, node) => (node.position.x > best.position.x ? node : best));
  const inColumn = nodes.filter((node) => Math.abs(node.position.x - rightmost.position.x) < 1);
  return { x: rightmost.position.x + 280, y: rightmost.position.y + inColumn.length * 110 };
}

function nodeCounts(nodes: Record<string, LocalNode>): Record<LocalNodeType, number> {
  const counts: Record<LocalNodeType, number> = {
    input: 0,
    agent: 0,
    llm: 0,
    tool: 0,
    http: 0,
    guardrail: 0,
    condition: 0,
    output: 0,
  };
  for (const node of Object.values(nodes)) {
    if (node.type in counts) counts[node.type] += 1;
  }
  return counts;
}

export default function GraphEditorPage() {
  const params = useParams<{ id: string }>();
  const agentId = params?.id ?? "";
  const toast = useToast();

  const agentApi = useApi<Agent>(agentId ? `/api/v1/agents/${agentId}` : null);
  const agent = agentApi.data;
  const graphApi = useApi<LocalGraphResponse>(
    agent?.provider === "langchain" ? `/api/v1/agents/${agentId}/graph` : null,
  );

  const [graph, setGraph] = useState<LocalGraph | null>(null);
  const [baseline, setBaseline] = useState("");
  const [revision, setRevision] = useState(0);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [revealNodeId, setRevealNodeId] = useState<string | null>(null);

  const [action, setAction] = useState<GraphAction>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [validation, setValidation] = useState<LocalGraphValidation | null>(null);

  const [runInput, setRunInput] = useState('{\n  "message": "Hello"\n}');
  const [runError, setRunError] = useState<string | null>(null);
  const [dryRun, setDryRun] = useState<LocalGraphDryRun | null>(null);

  const canEdit = Boolean(agent) && !agent?.archived_at;
  const dirty = graph !== null && snapshot(graph) !== baseline;
  const counts = useMemo(() => (graph ? nodeCounts(graph.nodes) : nodeCounts({})), [graph]);
  const selectedNode = graph && selectedId ? (graph.nodes[selectedId] ?? null) : null;

  const availableValues = useMemo(() => {
    if (!graph) return [];
    const values = new Set<string>();
    for (const node of Object.values(graph.nodes)) {
      if (node.type === "input") {
        for (const field of Array.isArray(node.config.fields)
          ? (node.config.fields as Array<{ name?: unknown }>)
          : []) {
          if (typeof field.name === "string" && field.name) values.add(field.name);
        }
      } else if (["llm", "http", "agent", "tool"].includes(node.type)) {
        if (typeof node.config.output_key === "string" && node.config.output_key) {
          values.add(node.config.output_key);
        }
      }
    }
    return Array.from(values);
  }, [graph]);

  useEffect(() => {
    if (!graphApi.data) return;
    const next = graphApi.data.graph;
    setGraph(next);
    setBaseline(snapshot(next));
    setRevision(graphApi.data.revision);
    setUpdatedAt(graphApi.data.updated_at);
    setSelectedId(null);
    setValidation(null);
    setActionError(null);
    setDryRun(null);
    setRunError(null);
  }, [graphApi.data]);

  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  const changeGraph = useCallback(
    (patch: Partial<Pick<LocalGraph, "nodes" | "edges">>) => {
      setGraph((current) => (current ? { ...current, ...patch } : current));
    },
    [],
  );

  function addNode(type: LocalNodeType) {
    if (!graph || !canEdit) return;
    if (type === "input" && counts.input > 0) {
      toast.push("A graph has exactly one input node.", "info");
      return;
    }
    const node = createNode(type, nextPosition(graph), graph.nodes);
    setGraph({ ...graph, nodes: { ...graph.nodes, [node.id]: node } });
    setSelectedId(node.id);
    setRevealNodeId(node.id);
    setValidation(null);
  }

  function updateNode(updated: LocalNode) {
    setGraph((current) =>
      current
        ? { ...current, nodes: { ...current.nodes, [updated.id]: updated } }
        : current,
    );
    setValidation(null);
  }

  function deleteNode(nodeId: string) {
    setGraph((current) => {
      if (!current) return current;
      const nodes = { ...current.nodes };
      delete nodes[nodeId];
      return {
        ...current,
        nodes,
        edges: current.edges.filter(
          (edge) => edge.source !== nodeId && edge.target !== nodeId,
        ),
      };
    });
    if (selectedId === nodeId) setSelectedId(null);
    setValidation(null);
  }

  async function validate() {
    if (!graph) return;
    setAction("validate");
    setActionError(null);
    try {
      const result = await api.post<LocalGraphValidation>(
        `/api/v1/agents/${agentId}/graph/validate`,
        { nodes: graph.nodes, edges: graph.edges },
      );
      setValidation(result);
      if (result.valid) {
        toast.push("Graph passed server validation.", "success");
      } else {
        toast.push(result.error?.message ?? "Graph validation failed.", "error");
      }
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setAction(null);
    }
  }

  async function save() {
    if (!graph) return;
    const problem = localGraphProblem(graph);
    if (problem) {
      setActionError(problem);
      return;
    }
    setAction("save");
    setActionError(null);
    try {
      const result = await api.put<LocalGraphResponse>(
        `/api/v1/agents/${agentId}/graph`,
        { nodes: graph.nodes, edges: graph.edges },
      );
      setGraph(result.graph);
      setBaseline(snapshot(result.graph));
      setRevision(result.revision);
      setUpdatedAt(result.updated_at);
      setValidation({ valid: true, error: null, graph: result.graph });
      toast.push("Draft graph saved to this platform.", "success");
    } catch (error) {
      setActionError(errorMessage(error));
    } finally {
      setAction(null);
    }
  }

  async function runDraft() {
    if (!graph) return;
    if (dirty) {
      setRunError("Save the draft before running it. The runtime executes the saved draft, not unsaved canvas edits.");
      return;
    }
    let parsed: unknown;
    try {
      parsed = JSON.parse(runInput);
    } catch {
      setRunError("Input must be valid JSON.");
      return;
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      setRunError('Input must be a JSON object, for example {"message": "Hello"}.');
      return;
    }
    setAction("run");
    setRunError(null);
    setDryRun(null);
    try {
      const result = await api.post<LocalGraphDryRun>(
        `/api/v1/agents/${agentId}/graph/dry_run`,
        { input: parsed },
      );
      setDryRun(result);
      if (result.run.status === "completed") {
        toast.push("Draft ran successfully and was recorded as a platform run.", "success");
      } else {
        toast.push("The draft run failed. Inspect the error and run detail.", "error");
      }
      agentApi.reload();
    } catch (error) {
      setRunError(errorMessage(error));
      agentApi.reload();
    } finally {
      setAction(null);
    }
  }

  function refresh() {
    graphApi.reload();
    agentApi.reload();
    setActionError(null);
    setRunError(null);
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

  if (agentApi.loading && !agent) return <LoadingBlock rows={7} />;
  if (!agent) {
    return <EmptyState title="Agent not found" description="This agent does not exist." />;
  }

  const backLink = (
    <Link href={`/agents/${agent.id}`} className="btn btn-ghost btn-sm wf-back">
      <Icon name="arrow-left" size={14} />
      <span>Back to {agent.name}</span>
    </Link>
  );

  if (agent.provider !== "langchain") {
    return (
      <div className="stack">
        {backLink}
        <EmptyState
          icon="workflow"
          title="This agent has no platform graph"
          description="Graphs are owned by the platform and run against an OpenAI-compatible model connection. Link this agent to a model provider first."
          action={
            <Link href={`/agents/${agent.id}`} className="btn btn-primary btn-sm">
              Open agent
            </Link>
          }
        />
      </div>
    );
  }

  if (graphApi.error) {
    return (
      <div className="stack">
        {backLink}
        <ErrorBlock message={graphApi.error} onRetry={graphApi.reload} />
        <Card title="What this editor needs" padded>
          <ul className="wf-bullets">
            <li>The agent must be linked to an OpenAI-compatible model connection.</li>
            <li>The connection needs a base URL, any API key value, and a model that GET /models lists.</li>
            <li>Graph edits are platform-owned; publishing snapshots the saved draft.</li>
          </ul>
        </Card>
      </div>
    );
  }

  if (!graph) return <LoadingBlock rows={8} />;

  const run = dryRun?.run ?? null;
  const steps = (run?.output?.provider_extension as { langchain?: { steps?: unknown } } | undefined)
    ?.langchain?.steps;

  return (
    <div className="stack-lg wf-page">
      <div className="wf-top">
        <div>
          {backLink}
          <div className="agent-title">
            <h1>Graph editor</h1>
            <Badge tone="accent">Platform graph</Badge>
            <Badge tone={revision > 0 ? "neutral" : "warning"} dot>
              {revision > 0 ? `Draft r${revision}` : "Default draft"}
            </Badge>
            {dirty ? (
              <Badge tone="warning" dot>
                Unsaved
              </Badge>
            ) : (
              <Badge tone="neutral" dot>
                Saved
              </Badge>
            )}
            {agent.archived_at ? <Badge tone="warning">Archived</Badge> : null}
          </div>
          <div className="agent-meta">
            <span>{agent.name}</span>
            <span aria-hidden="true">·</span>
            <span className="mono">{shortId(agent.id)}</span>
            <span aria-hidden="true">·</span>
            <span>{Object.keys(graph.nodes).length} nodes</span>
            <span aria-hidden="true">·</span>
            <span>updated {formatDateTime(updatedAt)}</span>
          </div>
        </div>
        <div className="page-actions">
          <Button variant="secondary" icon={<Icon name="refresh" size={15} />} onClick={refresh}>
            Refresh
          </Button>
          <Button
            variant="secondary"
            icon={<Icon name="check" size={15} />}
            loading={action === "validate"}
            disabled={!canEdit || action !== null}
            onClick={() => void validate()}
            title="Validate against the same rules used at publish time"
          >
            Validate
          </Button>
          <Button
            variant="secondary"
            icon={<Icon name="save" size={15} />}
            loading={action === "save"}
            disabled={!canEdit || !dirty || action !== null}
            onClick={() => void save()}
            title={dirty ? "Save this graph as the platform draft" : "No unsaved changes"}
          >
            Save draft
          </Button>
          <Button
            icon={<Icon name="play" size={15} />}
            loading={action === "run"}
            disabled={!canEdit || dirty || action !== null}
            onClick={() => void runDraft()}
            title={dirty ? "Save the draft before running it" : "Execute the saved draft with the real model"}
          >
            Run draft
          </Button>
          <Link href={`/agents/${agent.id}`} className="btn btn-ghost btn-md">
            <Icon name="bot" size={15} />
            <span>Agent</span>
          </Link>
        </div>
      </div>

      {agent.archived_at ? (
        <div className="panel">
          <p className="panel-title">Read-only agent</p>
          <p className="panel-text">
            This agent is archived. The graph can be inspected, but editing, saving, and running are
            disabled.
          </p>
        </div>
      ) : null}

      {actionError ? <InlineError message={actionError} /> : null}
      {validation && !validation.valid ? (
        <InlineError
          message={
            validation.error?.node_id
              ? `${validation.error.message} (node: ${validation.error.node_id})`
              : (validation.error?.message ?? "Graph validation failed.")
          }
        />
      ) : null}
      {validation?.valid ? (
        <div className="graph-validation-ok">
          <Icon name="check" size={15} />
          <span>Server validation passed. Save or run the draft when you are ready.</span>
        </div>
      ) : null}

      <div className={`wf-shell ${selectedId ? "has-selection" : ""}`}>
        <LocalGraphPalette counts={counts} disabled={!canEdit} onAdd={addNode} />

        <div className="wf-main">
          <div className="wf-statusbar">
            <div className="row-wrap">
              <Badge tone="neutral">
                {counts.input} input · {counts.agent} agent · {counts.llm} llm · {counts.tool} tool ·{" "}
                {counts.guardrail} guardrail · {counts.condition} condition · {counts.output} output
              </Badge>
              {dirty ? <Badge tone="warning">Unsaved canvas edits</Badge> : null}
              {revision === 0 ? (
                <Badge tone="warning">Not yet persisted</Badge>
              ) : (
                <Badge tone="success">Draft r{revision}</Badge>
              )}
            </div>
            <div className="row">
              <span className="small faint">
                {Object.keys(graph.nodes).length} / 60 nodes · {graph.edges.length} / 120 edges
              </span>
            </div>
          </div>

          <LocalGraphCanvas
            graph={graph}
            readOnly={!canEdit}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onChange={changeGraph}
            onNotice={(message) => toast.push(message, "info")}
            revealNodeId={revealNodeId}
          />
        </div>

        <LocalGraphInspector
          node={selectedNode}
          readOnly={!canEdit}
          availableValues={availableValues}
          onChange={updateNode}
          onDelete={deleteNode}
          onClose={() => setSelectedId(null)}
        />
      </div>

      <Card
        title="Run the saved draft"
        description="Executes the real LangGraph runtime with the linked model. The run is recorded and visible in Runs."
      >
        <div className="grid-main">
          <div className="stack">
            <Field
              label="Input (JSON object)"
              htmlFor="graph-run-input"
              hint="Must satisfy the input node's required fields. Extra keys are preserved."
            >
              <Textarea
                id="graph-run-input"
                className="textarea-mono"
                rows={7}
                spellCheck={false}
                value={runInput}
                onChange={(event) => setRunInput(event.target.value)}
              />
            </Field>
            {runError ? <InlineError message={runError} /> : null}
            <div className="row">
              <Button
                loading={action === "run"}
                disabled={!canEdit || dirty || action !== null}
                icon={<Icon name="play" size={15} />}
                onClick={() => void runDraft()}
              >
                Run draft
              </Button>
              {dirty ? (
                <span className="small faint">Save the draft first; the runtime never reads unsaved canvas state.</span>
              ) : null}
            </div>
          </div>

          <div className="stack">
            {run ? (
              <>
                <div className="row-wrap">
                  <StatusBadge status={run.status} />
                  <span className="small muted">{formatDuration(run.duration_ms)}</span>
                  <span className="small faint">
                    tokens {formatNumber(run.token_count)}
                    {run.token_count_is_estimate ? " (estimate)" : " (reported)"}
                  </span>
                  <Link href={`/runs/${run.run_id}`} className="small">
                    Inspect run
                  </Link>
                </div>
                {run.status === "failed" ? (
                  <div className="panel" style={{ borderColor: "rgba(248,113,113,0.35)" }}>
                    <p className="panel-title text-danger">
                      {run.error_category ?? "Graph failed"}
                    </p>
                    <p className="panel-text">{run.error_message ?? "No message recorded."}</p>
                  </div>
                ) : (
                  <pre className="test-output">{runMessage(run) ?? "No message output."}</pre>
                )}
                {Array.isArray(steps) && steps.length > 0 ? (
                  <details className="wf-raw">
                    <summary>Execution steps</summary>
                    <pre className="test-output">{jsonPreview(steps, 8000)}</pre>
                  </details>
                ) : null}
              </>
            ) : (
              <EmptyState
                compact
                icon="play"
                title="No draft run yet"
                description="A successful run proves the saved graph and the model credential together."
              />
            )}
          </div>
        </div>
      </Card>

      <Card title="What runs where" padded>
        <ul className="wf-bullets">
          <li>
            The graph is stored in this platform. <strong>Save draft</strong> persists the editable
            graph; <strong>Publish</strong> (on the agent page) snapshots the saved draft into an
            immutable version.
          </li>
          <li>
            The gateway executes only the published snapshot. Test and draft runs execute the
            saved draft, so editing after publishing does not change live traffic until you publish
            again.
          </li>
          <li>
            <span className="mono">agent</span> nodes call the model, attach the selected tools and
            skills, and loop through real tool calls up to the step limit.{" "}
            <span className="mono">tool</span> and <span className="mono">http</span> nodes make real
            outbound requests. Nothing is simulated.
          </li>
          <li>
            Graphs are acyclic and cannot merge branches. Conditions and guardrails have exactly two
            outgoing branches, and every branch must end at an output node so a rejected answer is
            still visible.
          </li>
        </ul>
        <div className="row-wrap small muted" style={{ marginTop: 12 }}>
          {NODE_ORDER.map((type) => (
            <span className="capability-chip" key={type}>
              <strong>{NODE_META[type].label}:</strong> {NODE_META[type].description}
            </span>
          ))}
        </div>
      </Card>
    </div>
  );
}
