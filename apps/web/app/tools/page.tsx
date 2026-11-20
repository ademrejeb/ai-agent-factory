"use client";

import { useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useToast } from "@/components/providers/ToastProvider";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import type { ListResponse, McpTool, Tool } from "@/lib/types";

type Kind = "http" | "mcp";

const HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"];

function parseJson(value: string, label: string): unknown {
  try {
    return JSON.parse(value || "null");
  } catch {
    throw new Error(`${label} must be valid JSON.`);
  }
}

export default function ToolsPage() {
  const toast = useToast();
  const tools = useApi<ListResponse<Tool>>("/api/v1/tools");
  const [editing, setEditing] = useState<Tool | null>(null);
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("http");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("https://");
  const [method, setMethod] = useState("GET");
  const [mcpTool, setMcpTool] = useState("");
  const [headers, setHeaders] = useState("");
  const [inputSchema, setInputSchema] = useState(
    '{\n  "type": "object",\n  "properties": {\n    "query": { "type": "string" }\n  },\n  "required": ["query"]\n}',
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testArgs, setTestArgs] = useState('{\n  "query": "E30"\n}');
  const [testResult, setTestResult] = useState<string | null>(null);
  const [discovered, setDiscovered] = useState<McpTool[]>([]);
  const [discovering, setDiscovering] = useState(false);

  function reset() {
    setEditing(null);
    setName("");
    setKind("http");
    setDescription("");
    setUrl("https://");
    setMethod("GET");
    setMcpTool("");
    setHeaders("");
    setInputSchema(
      '{\n  "type": "object",\n  "properties": {\n    "query": { "type": "string" }\n  },\n  "required": ["query"]\n}',
    );
    setError(null);
    setTestResult(null);
    setDiscovered([]);
  }

  function edit(tool: Tool) {
    setEditing(tool);
    setName(tool.name);
    setKind(tool.kind);
    setDescription(tool.description);
    setUrl(String(tool.config.url ?? tool.config.server_url ?? ""));
    setMethod(String(tool.config.method ?? "GET"));
    setMcpTool(String(tool.config.tool_name ?? ""));
    setHeaders("");
    setInputSchema(JSON.stringify(tool.input_schema, null, 2));
    setError(null);
    setTestResult(null);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const parsedHeaders = headers.trim()
        ? (parseJson(headers, "Headers") as Record<string, string>)
        : undefined;
      const parsedSchema = parseJson(inputSchema, "Input schema") as Record<string, unknown>;
      const config =
        kind === "http"
          ? { method, url, timeout_seconds: 30 }
          : { server_url: url, tool_name: mcpTool, timeout_seconds: 30 };
      const body: Record<string, unknown> = {
        name,
        kind,
        description,
        config,
        input_schema: parsedSchema,
      };
      if (parsedHeaders !== undefined) body.headers = parsedHeaders;
      if (editing) {
        await api.patch(`/api/v1/tools/${editing.id}`, body);
        toast.push("Tool updated.", "success");
      } else {
        await api.post("/api/v1/tools", body);
        toast.push("Tool created. Attach it to an agent node in the graph editor.", "success");
      }
      reset();
      tools.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(tool: Tool) {
    if (!window.confirm(`Delete tool "${tool.name}"? Graphs referencing it will fail validation.`)) {
      return;
    }
    try {
      await api.del(`/api/v1/tools/${tool.id}`);
      toast.push("Tool deleted.", "success");
      tools.reload();
    } catch (err) {
      toast.push(errorMessage(err), "error");
    }
  }

  async function test(tool: Tool) {
    setBusy(true);
    setError(null);
    setTestResult(null);
    try {
      const args = parseJson(testArgs, "Test arguments") as Record<string, unknown>;
      const result = await api.post<{ result: unknown }>(
        `/api/v1/tools/${tool.id}/test`,
        { arguments: args },
      );
      setTestResult(JSON.stringify(result.result, null, 2));
      toast.push("The tool answered. This is the same path an agent node uses.", "success");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function discover() {
    setDiscovering(true);
    setError(null);
    try {
      const parsedHeaders = parseJson(headers, "Headers") as Record<string, string>;
      const result = await api.post<{ items: McpTool[] }>("/api/v1/tools/discover/mcp", {
        server_url: url,
        headers: parsedHeaders,
      });
      setDiscovered(result.items);
      toast.push(`${result.items.length} MCP tools discovered.`, "success");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setDiscovering(false);
    }
  }

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Capabilities"
        title="Tools & MCP"
        description="Reusable HTTP and MCP tools. An agent node sees exactly the tools you attach, with the arguments and descriptions defined here."
        actions={
          <Button variant="secondary" icon={<Icon name="refresh" size={15} />} onClick={tools.reload}>
            Refresh
          </Button>
        }
      />

      <div className="grid-main">
        <Card
          title="Tool registry"
          description="Organization-scoped. Secrets in headers are encrypted and never returned."
          padded={false}
        >
          {tools.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={tools.error} onRetry={tools.reload} />
            </div>
          ) : tools.loading && !tools.data ? (
            <LoadingBlock rows={5} />
          ) : (tools.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              icon="terminal"
              title="No tools yet"
              description="Create an HTTP tool or connect an MCP server. Tools can then be attached to agent nodes."
            />
          ) : (
            <ul className="list-plain">
              {tools.data?.items.map((tool) => (
                <li className="list-item" key={tool.id}>
                  <div>
                    <p className="list-item-title">
                      {tool.name}{" "}
                      <Badge tone={tool.kind === "mcp" ? "accent" : "neutral"}>
                        {tool.kind.toUpperCase()}
                      </Badge>{" "}
                      {!tool.enabled ? <Badge tone="warning">disabled</Badge> : null}
                    </p>
                    <p className="list-item-meta">
                      {tool.description || "No description. The model uses this text to decide when to call it."}
                    </p>
                    <p className="list-item-meta mono">
                      {tool.kind === "http"
                        ? `${String(tool.config.method ?? "GET")} ${String(tool.config.url ?? "")}`
                        : `${String(tool.config.server_url ?? "")} · ${String(tool.config.tool_name ?? "")}`}
                    </p>
                    {tool.headers_configured.length > 0 ? (
                      <p className="list-item-meta">
                        Headers configured: <span className="mono">{tool.headers_configured.join(", ")}</span>
                      </p>
                    ) : null}
                  </div>
                  <div className="stack-sm" style={{ alignItems: "flex-end" }}>
                    <Button size="sm" variant="secondary" onClick={() => edit(tool)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void test(tool)}>
                      Test
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void remove(tool)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="stack">
          <Card title={editing ? `Edit ${editing.name}` : "Add a tool"}>
            <form className="stack" onSubmit={save}>
              {error ? <InlineError message={error} /> : null}
              <Field label="Name" htmlFor="tool-name" required>
                <Input
                  id="tool-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Look up a diagnostic code"
                  required
                />
              </Field>
              <Field label="Kind" htmlFor="tool-kind">
                <Select
                  id="tool-kind"
                  value={kind}
                  onChange={(event) => setKind(event.target.value as Kind)}
                >
                  <option value="http">HTTP request</option>
                  <option value="mcp">MCP server tool</option>
                </Select>
              </Field>
              <Field
                label="Description the model sees"
                htmlFor="tool-description"
                hint="Say when to use it, not just what it is."
              >
                <Textarea
                  id="tool-description"
                  rows={3}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </Field>
              <Field label={kind === "http" ? "URL" : "MCP server URL"} htmlFor="tool-url" required>
                <Input id="tool-url" value={url} onChange={(event) => setUrl(event.target.value)} required />
              </Field>
              {kind === "http" ? (
                <Field label="Method" htmlFor="tool-method">
                  <Select id="tool-method" value={method} onChange={(event) => setMethod(event.target.value)}>
                    {HTTP_METHODS.map((item) => (
                      <option key={item} value={item}>{item}</option>
                    ))}
                  </Select>
                </Field>
              ) : (
                <Field
                  label="Remote tool name"
                  htmlFor="tool-mcp-name"
                  hint="Discover first if you do not know it."
                >
                  <div className="row">
                    <Input
                      id="tool-mcp-name"
                      value={mcpTool}
                      onChange={(event) => setMcpTool(event.target.value)}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      loading={discovering}
                      onClick={() => void discover()}
                    >
                      Discover
                    </Button>
                  </div>
                </Field>
              )}
              {discovered.length > 0 ? (
                <div className="graph-token-list">
                  {discovered.map((item) => (
                    <button
                      type="button"
                      className="graph-token"
                      key={item.name}
                      onClick={() => setMcpTool(item.name)}
                      title={item.description}
                    >
                      {item.name}
                    </button>
                  ))}
                </div>
              ) : null}
              <Field
                label="Headers (JSON)"
                htmlFor="tool-headers"
                hint="Use {{secrets.NAME}} for authorization. Values are encrypted at rest."
              >
                <Textarea
                  id="tool-headers"
                  className="textarea-mono"
                  rows={4}
                  spellCheck={false}
                  value={headers}
                  placeholder={'{\n  "Authorization": "Bearer {{secrets.tool_key}}"\n}'}
                  onChange={(event) => setHeaders(event.target.value)}
                />
              </Field>
              <Field
                label="Input schema (JSON Schema)"
                htmlFor="tool-schema"
                hint="The model fills these arguments. Keep the surface small and explicit."
              >
                <Textarea
                  id="tool-schema"
                  className="textarea-mono"
                  rows={8}
                  spellCheck={false}
                  value={inputSchema}
                  onChange={(event) => setInputSchema(event.target.value)}
                />
              </Field>
              <div className="row">
                <Button type="submit" loading={busy}>
                  {editing ? "Save changes" : "Create tool"}
                </Button>
                {editing ? (
                  <Button type="button" variant="ghost" onClick={reset}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </form>
          </Card>

          <Card
            title="Test the exact tool path"
            description="Runs the same executor an agent uses. Nothing is mocked."
          >
            <Field label="Arguments (JSON)" htmlFor="tool-test-args">
              <Textarea
                id="tool-test-args"
                className="textarea-mono"
                rows={4}
                value={testArgs}
                onChange={(event) => setTestArgs(event.target.value)}
              />
            </Field>
            <p className="small faint" style={{ marginTop: 8 }}>
              Use Edit on a tool first, then Test. The result is truncated only by the response-size guard.
            </p>
            {testResult ? <pre className="test-output">{testResult}</pre> : null}
          </Card>
        </div>
      </div>
    </div>
  );
}
