"use client";

import { useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { useToast } from "@/components/providers/ToastProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import { formatDateTime, titleCase } from "@/lib/format";
import type { ListResponse, Workspace } from "@/lib/types";

export default function WorkspacesPage() {
  const { me } = useAuth();
  const toast = useToast();
  const workspaces = useApi<ListResponse<Workspace>>("/api/v1/workspaces");
  const [name, setName] = useState("");
  const [kind, setKind] = useState("experiment");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canManage = me?.role === "owner" || me?.role === "admin";
  const items = workspaces.data?.items ?? [];

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const workspace = await api.post<Workspace>("/api/v1/workspaces", {
        name: name.trim(),
        kind,
      });
      toast.push(`Workspace “${workspace.name}” created.`, "success");
      setName("");
      workspaces.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Organization"
        title="Workspaces"
        description="Group agents by intent. Workspaces belong to your organization and are enforced by the API."
        actions={
          <Button
            variant="secondary"
            icon={<Icon name="refresh" size={15} />}
            onClick={workspaces.reload}
            loading={workspaces.loading}
          >
            Refresh
          </Button>
        }
      />

      {workspaces.error ? (
        <ErrorBlock message={workspaces.error} onRetry={workspaces.reload} />
      ) : null}

      <div className="grid-main">
        <Card title="All workspaces" padded={false}>
          {workspaces.loading && !workspaces.data ? (
            <LoadingBlock rows={4} />
          ) : items.length === 0 ? (
            <EmptyState
              icon="layers"
              title="No workspaces"
              description="Every organization is created with a default “Experiments” workspace. Create another for production agents."
            />
          ) : (
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Slug</th>
                    <th>Kind</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((workspace) => (
                    <tr key={workspace.id}>
                      <td>{workspace.name}</td>
                      <td className="cell-mono">{workspace.slug}</td>
                      <td>
                        <Badge tone={workspace.kind === "production" ? "info" : "neutral"}>
                          {titleCase(workspace.kind)}
                        </Badge>
                      </td>
                      <td className="muted nowrap">{formatDateTime(workspace.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <Card title="Create workspace">
          {!canManage ? (
            <div className="panel">
              <p className="panel-title">Owner or admin required</p>
              <p className="panel-text">
                Your role is <span className="mono">{me?.role ?? "unknown"}</span>. Ask an
                organization owner to create workspaces.
              </p>
            </div>
          ) : (
            <form className="stack" onSubmit={create} noValidate>
              {error ? <InlineError message={error} /> : null}
              <Field label="Name" htmlFor="workspace-name" required>
                <Input
                  id="workspace-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="Production"
                  required
                />
              </Field>
              <Field
                label="Kind"
                htmlFor="workspace-kind"
                hint="A label for operators. It does not change provider behaviour."
              >
                <Select
                  id="workspace-kind"
                  value={kind}
                  onChange={(event) => setKind(event.target.value)}
                >
                  <option value="experiment">Experiment</option>
                  <option value="production">Production</option>
                </Select>
              </Field>
              <Button type="submit" loading={busy} disabled={!name.trim()}>
                Create workspace
              </Button>
            </form>
          )}
          <div className="divider" />
          <p className="small faint">
            Workspace deletion and renaming are not implemented yet. Agents keep their workspace
            reference for auditability.
          </p>
        </Card>
      </div>
    </div>
  );
}
