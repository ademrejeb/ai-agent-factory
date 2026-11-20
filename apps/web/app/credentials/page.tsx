"use client";

import Link from "next/link";
import { useState } from "react";

import { useToast } from "@/components/providers/ToastProvider";
import { Badge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CodeBlock, CopyButton } from "@/components/ui/CodeBlock";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Field, Input } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { ApiCredential, ListResponse } from "@/lib/types";

export default function CredentialsPage() {
  const toast = useToast();
  const credentials = useApi<ListResponse<ApiCredential>>("/api/v1/credentials");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<ApiCredential | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<ApiCredential | null>(null);
  const [revoking, setRevoking] = useState(false);

  const items = credentials.data?.items ?? [];

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const credential = await api.post<ApiCredential>("/api/v1/credentials", {
        name: name.trim(),
        scopes: ["agents:run"],
      });
      setCreateOpen(false);
      setName("");
      setCreated(credential);
      credentials.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function revoke() {
    if (!revokeTarget) return;
    setRevoking(true);
    try {
      await api.post(`/api/v1/credentials/${revokeTarget.id}/revoke`);
      toast.push("Credential revoked. Calls with this key will now fail.", "success");
      setRevokeTarget(null);
      credentials.reload();
    } catch (err) {
      toast.push(errorMessage(err), "error");
    } finally {
      setRevoking(false);
    }
  }

  const sample = `curl -X POST "$API_BASE/api/v1/agents/AGENT_ID/runs" \\
  -H "Authorization: Bearer aaf_..." \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: demo-1" \\
  -d '{"input":{"message":"How do I reset my password?"}}'`;

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Access"
        title="API keys"
        description="Scoped customer credentials for the execution gateway. Secrets are hashed at rest and shown only once at creation."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<Icon name="refresh" size={15} />}
              onClick={credentials.reload}
              loading={credentials.loading}
            >
              Refresh
            </Button>
            <Button onClick={() => setCreateOpen(true)} icon={<Icon name="plus" size={15} />}>
              New API key
            </Button>
          </>
        }
      />

      {credentials.error ? (
        <ErrorBlock message={credentials.error} onRetry={credentials.reload} />
      ) : null}

      <Card title="Credentials" padded={false}>
        {credentials.loading && !credentials.data ? (
          <LoadingBlock rows={4} />
        ) : items.length === 0 ? (
          <EmptyState
            icon="key"
            title="No API keys yet"
            description="Create a key to call published agents through the gateway. The full secret is displayed once."
            action={
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                Create the first key
              </Button>
            }
          />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Prefix</th>
                  <th>Scopes</th>
                  <th>Status</th>
                  <th>Last used</th>
                  <th>Created</th>
                  <th className="table-actions">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((credential) => (
                  <tr key={credential.id}>
                    <td>{credential.name}</td>
                    <td className="cell-mono">{credential.prefix}…</td>
                    <td>
                      <div className="row-wrap">
                        {credential.scopes.map((scope) => (
                          <span className="tag" key={scope}>
                            {scope}
                          </span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <StatusBadge
                        status={credential.revoked_at ? "revoked" : "active"}
                        label={credential.revoked_at ? "Revoked" : "Active"}
                      />
                    </td>
                    <td className="muted nowrap">{formatDateTime(credential.last_used_at)}</td>
                    <td className="muted nowrap">{formatDateTime(credential.created_at)}</td>
                    <td className="table-actions">
                      {credential.revoked_at ? (
                        <span className="small faint">Revoked</span>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setRevokeTarget(credential)}
                          icon={<Icon name="trash" size={13} />}
                        >
                          Revoke
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Quick start" description="Endpoint and authentication for customer applications.">
        <div className="stack">
          <div className="row-wrap small muted">
            <Badge tone="info">POST</Badge>
            <span className="mono">/api/v1/agents/{"{agent_id}"}/runs</span>
            <span>·</span>
            <span>scope</span>
            <span className="mono">agents:run</span>
            <span>·</span>
            <Link href="/docs">Full API reference</Link>
          </div>
          <CodeBlock code={sample} language="bash" />
          <p className="small faint">
            The agent must be published or monitored with an active deployment. Pass an{" "}
            <span className="mono">Idempotency-Key</span> header to make retries safe for the same
            credential.
          </p>
        </div>
      </Card>

      <Modal
        open={createOpen}
        title="Create API key"
        description="The gateway accepts this key as a Bearer token. Only the agents:run scope is enforced in this release."
        onClose={() => {
          if (!busy) setCreateOpen(false);
        }}
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => setCreateOpen(false)}
              disabled={busy}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="create-credential-form"
              loading={busy}
              disabled={!name.trim()}
            >
              Create key
            </Button>
          </>
        }
      >
        <form id="create-credential-form" className="stack" onSubmit={create} noValidate>
          {error ? <InlineError message={error} /> : null}
          <Field
            label="Key name"
            htmlFor="credential-name"
            hint="Use a name that identifies the calling system, for example “customer-portal”."
            required
          >
            <Input
              id="credential-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="customer-portal"
              required
              autoFocus
            />
          </Field>
          <div className="panel">
            <p className="panel-title">Scope</p>
            <p className="panel-text">
              <span className="mono">agents:run</span> — execute published agents and read runs
              belonging to this organization.
            </p>
          </div>
        </form>
      </Modal>

      <Modal
        open={Boolean(created)}
        title="Copy your API key now"
        description="This is the only time the secret is returned. It is stored as a hash and cannot be recovered."
        onClose={() => setCreated(null)}
        footer={
          <Button variant="secondary" onClick={() => setCreated(null)}>
            I have stored the key
          </Button>
        }
      >
        {created ? (
          <div className="stack">
            <Field label="Secret" htmlFor="created-secret" hint={created.warning}>
              <Input
                id="created-secret"
                readOnly
                value={created.secret ?? ""}
                className="mono"
                onFocus={(event) => event.target.select()}
              />
            </Field>
            <div className="row">
              <CopyButton value={created.secret ?? ""} label="Copy secret" />
            </div>
            <p className="small faint">
              Prefix <span className="mono">{created.prefix}</span> is safe to display for
              identification.
            </p>
          </div>
        ) : null}
      </Modal>

      <ConfirmDialog
        open={Boolean(revokeTarget)}
        title="Revoke this API key?"
        message={`Requests using ${revokeTarget?.name ?? "this key"} will be rejected immediately. This cannot be undone.`}
        confirmLabel="Revoke key"
        loading={revoking}
        onConfirm={revoke}
        onClose={() => setRevokeTarget(null)}
      />
    </div>
  );
}
