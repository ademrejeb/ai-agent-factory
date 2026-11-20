"use client";

import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/providers/ToastProvider";
import { StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import {
  capabilityLabel,
  capabilityValue,
  formatDateTime,
  providerConsoleUrl,
  titleCase,
} from "@/lib/format";
import type {
  ListResponse,
  ProviderConnection,
  ProviderDescriptor,
} from "@/lib/types";

export default function ProvidersPage() {
  const toast = useToast();
  const catalog = useApi<ListResponse<ProviderDescriptor>>("/api/v1/providers");
  const connections = useApi<ListResponse<ProviderConnection>>("/api/v1/provider-connections");

  const [descriptor, setDescriptor] = useState<ProviderDescriptor | null>(null);
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [workspaceId, setWorkspaceId] = useState("");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [checking, setChecking] = useState<string | null>(null);
  const [models, setModels] = useState<Record<string, string[]>>({});
  const [loadingModels, setLoadingModels] = useState<string | null>(null);

  function openModal(provider: ProviderDescriptor) {
    setDescriptor(provider);
    setName(`${provider.name} (local)`);
    setBaseUrl(provider.base_url_placeholder);
    setApiKey("");
    setWorkspaceId("");
    setModel("");
    setFormError(null);
  }

  function openOllama() {
    const provider = catalog.data?.items.find((item) => item.id === "langchain");
    if (!provider) return;
    setDescriptor(provider);
    setName("Ollama (local)");
    setBaseUrl("http://localhost:11434/v1");
    setApiKey("ollama");
    setModel("qwen2.5-coder:7b");
    setFormError(null);
  }

  async function loadModels(connection: ProviderConnection) {
    setLoadingModels(connection.id);
    try {
      const data = await api.get<{ models: string[]; warning: string | null }>(
        `/api/v1/provider-connections/${connection.id}/models`,
      );
      setModels((current) => ({ ...current, [connection.id]: data.models }));
      if (data.warning) toast.push(data.warning, "info");
      if (data.models.length === 0) toast.push("The endpoint returned no models.", "info");
    } catch (error) {
      toast.push(errorMessage(error), "error");
    } finally {
      setLoadingModels(null);
    }
  }

  function closeModal() {
    if (busy) return;
    setDescriptor(null);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!descriptor) return;
    setBusy(true);
    setFormError(null);
    try {
      const connection = await api.post<ProviderConnection>("/api/v1/provider-connections", {
        provider: descriptor.id,
        name: name.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey || "ollama",
        workspace_id: descriptor.requires_workspace_id ? workspaceId.trim() : undefined,
        model: descriptor.requires_model ? model.trim() : undefined,
      });
      if (connection.status.startsWith("connected")) {
        toast.push(`Connected to ${descriptor.name}.`, "success");
      } else {
        toast.push(
          `Connection saved with status "${connection.status}". Check the detail below.`,
          "error",
        );
      }
      setDescriptor(null);
      connections.reload();
    } catch (error) {
      setFormError(errorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  async function check(connection: ProviderConnection) {
    setChecking(connection.id);
    try {
      const updated = await api.post<ProviderConnection>(
        `/api/v1/provider-connections/${connection.id}/check`,
      );
      if (updated.status.startsWith("connected")) {
        toast.push(`${updated.name} is reachable.`, "success");
      } else {
        toast.push(
          updated.last_error ?? `Check returned status "${updated.status}".`,
          "error",
        );
      }
      connections.reload();
    } catch (error) {
      toast.push(errorMessage(error), "error");
    } finally {
      setChecking(null);
    }
  }

  const items = connections.data?.items ?? [];

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Integrations"
        title="Model providers"
        description="The model endpoint behind your agents. Credentials are encrypted at rest and never returned to this browser. Local Ollama needs no account."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<Icon name="refresh" size={15} />}
              onClick={() => {
                catalog.reload();
                connections.reload();
              }}
              loading={connections.loading || catalog.loading}
            >
              Refresh
            </Button>
            <Button icon={<Icon name="plus" size={15} />} onClick={openOllama}>
              Use local Ollama
            </Button>
          </>
        }
      />

      {catalog.error ? <ErrorBlock message={catalog.error} onRetry={catalog.reload} /> : null}
      {connections.error ? (
        <ErrorBlock message={connections.error} onRetry={connections.reload} />
      ) : null}

      <div className="provider-grid">
        {catalog.loading && !catalog.data
          ? Array.from({ length: 2 }).map((_, index) => (
              <div className="provider-card" key={index}>
                <LoadingBlock rows={4} />
              </div>
            ))
          : (catalog.data?.items ?? []).map((provider) => {
              const providerConnections = items.filter((conn) => conn.provider === provider.id);
              return (
                <section className="provider-card" key={provider.id}>
                  <div className="provider-card-head">
                    <div className="row">
                      <span className="provider-mark">{provider.name.slice(0, 2).toUpperCase()}</span>
                      <div>
                        <h2 className="provider-name">{provider.name}</h2>
                        <p className="provider-summary">{provider.summary}</p>
                      </div>
                    </div>
                    <Button size="sm" onClick={() => openModal(provider)}>
                      Add connection
                    </Button>
                  </div>

                  <div className="capability-list">
                    {Object.entries(provider.capabilities).map(([key, value]) => (
                      <span className="capability-chip" key={key}>
                        <strong>{capabilityLabel(key)}:</strong> {capabilityValue(value)}
                      </span>
                    ))}
                  </div>

                  <div className="stack-sm">
                    {provider.limitations.map((limitation) => (
                      <p className="provider-limit" key={limitation}>
                        {limitation}
                      </p>
                    ))}
                  </div>

                  <a
                    className="small"
                    href={provider.docs_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Provider API documentation
                    <Icon name="arrow-up-right" size={13} style={{ marginLeft: 4 }} />
                  </a>

                  <div className="divider" style={{ margin: "2px 0" }} />

                  {providerConnections.length === 0 ? (
                    <p className="small faint">No connection configured.</p>
                  ) : (
                    <div className="stack-sm">
                      {providerConnections.map((connection) => (
                        <div className="panel" key={connection.id}>
                          <div className="row-between">
                            <div>
                              <p className="list-item-title">{connection.name}</p>
                              <p className="list-item-meta mono">{connection.base_url}</p>
                            </div>
                            <StatusBadge status={connection.status} />
                          </div>
                          {connection.last_error ? (
                            <p className="small text-danger" style={{ marginTop: 6 }}>
                              {connection.last_error}
                            </p>
                          ) : null}
                          <div className="row-wrap" style={{ marginTop: 8 }}>
                            <span className="small faint">
                              checked {formatDateTime(connection.last_checked_at)}
                            </span>
                            <span className="toolbar-spacer" />
                            <a
                              className="small"
                              href={providerConsoleUrl(connection.base_url)}
                              target="_blank"
                              rel="noreferrer"
                            >
                              Console
                            </a>
                            <Button
                              variant="secondary"
                              size="sm"
                              loading={checking === connection.id}
                              onClick={() => void check(connection)}
                            >
                              Check now
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              loading={loadingModels === connection.id}
                              onClick={() => void loadModels(connection)}
                            >
                              List models
                            </Button>
                          </div>
                          {connection.extra_config?.mode || connection.extra_config?.model ? (
                            <p className="small faint" style={{ marginTop: 6 }}>
                              {connection.extra_config?.model
                                ? `Model: ${String(connection.extra_config.model)}`
                                : null}
                              {connection.extra_config?.mode
                                ? ` · ${titleCase(String(connection.extra_config.mode))} app`
                                : null}
                            </p>
                          ) : null}
                          {connection.extra_config?.warning ? (
                            <p className="small text-warning" style={{ marginTop: 6 }}>
                              {String(connection.extra_config.warning)}
                            </p>
                          ) : null}
                          {models[connection.id]?.length ? (
                            <div className="graph-token-list" style={{ marginTop: 8 }}>
                              {models[connection.id].slice(0, 30).map((available) => (
                                <span className="graph-token" key={available}>
                                  {available}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  )}
                </section>
              );
            })}
      </div>

      <Card title="How connections work">
        <div className="grid-2">
          <div className="panel">
            <p className="panel-title">Credentials</p>
            <p className="panel-text">
              The API key is stored encrypted with the platform secret key and is never included in
              list or detail responses. Base URL and key are fixed after creation; create a new
              connection to rotate them.
            </p>
          </div>
          <div className="panel">
            <p className="panel-title">Health is not assumed</p>
            <p className="panel-text">
              <span className="mono">connected</span> means the last check reached the provider and
              authenticated. <span className="mono">connected_limited</span> means the provider
              responded but the selected resource cannot be executed by this gateway.
            </p>
          </div>
        </div>
        {items.length === 0 ? (
          <div style={{ marginTop: 16 }}>
            <EmptyState
              compact
              icon="plug"
              title="No model endpoint configured"
              description="Use local Ollama for the fastest start, or connect any OpenAI-compatible endpoint. The platform will show the models it really found."
            />
          </div>
        ) : (
          <p className="small faint" style={{ marginTop: 14 }}>
            Next: <Link href="/agents/new">create an agent</Link>, link this model connection, then
            open the graph editor to attach tools, skills, and guardrails.
          </p>
        )}
      </Card>

      <Modal
        open={Boolean(descriptor)}
        title={descriptor ? `Connect ${descriptor.name}` : "Connect provider"}
        description={descriptor?.setup}
        onClose={closeModal}
        footer={
          <>
            <Button variant="secondary" onClick={closeModal} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="provider-connection-form"
              loading={busy}
              disabled={
                !name.trim() ||
                !baseUrl.trim() ||
                Boolean(descriptor?.requires_model && !model.trim())
              }
            >
              Save and verify
            </Button>
          </>
        }
      >
        <form id="provider-connection-form" className="stack" onSubmit={submit} noValidate>
          {formError ? <InlineError message={formError} /> : null}
          <Field label="Connection name" htmlFor="connection-name" required>
            <Input
              id="connection-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Ollama (local)"
              required
              autoFocus
            />
          </Field>
          <Field
            label="Base URL"
            htmlFor="connection-base-url"
            hint={descriptor?.base_url_help}
            required
          >
            <Input
              id="connection-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={descriptor?.base_url_placeholder}
              required
            />
          </Field>
          {descriptor?.requires_model ? (
            <Field
              label="Default model"
              htmlFor="connection-model"
              hint="The exact chat model this endpoint serves. After saving, use List models to see what Ollama actually has pulled. Graph nodes may override it."
              required
            >
              <Input
                id="connection-model"
                value={model}
                onChange={(event) => setModel(event.target.value)}
                placeholder="qwen2.5:7b"
                required
              />
            </Field>
          ) : null}
          <Field
            label={descriptor?.auth_label ?? "API key"}
            htmlFor="connection-api-key"
            hint="Stored encrypted and never displayed again. Local Ollama accepts any value; leave empty and the platform uses 'ollama'."
          >
            <Input
              id="connection-api-key"
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder="ollama"
            />
          </Field>
          <div className="panel">
            <p className="panel-title">What is verified on save</p>
            <p className="panel-text">
              The platform calls <span className="mono">GET /models</span> on the endpoint. If it
              cannot be reached, no connection is stored. If it answers but the model is missing,
              the connection is saved with a warning so you can fix it. Local Ollama usually needs
              no key at all.
            </p>
          </div>
        </form>
      </Modal>
    </div>
  );
}
