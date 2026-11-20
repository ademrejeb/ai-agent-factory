"use client";

import { useAuth } from "@/components/providers/AuthProvider";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CopyButton } from "@/components/ui/CodeBlock";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { LoadingBlock } from "@/components/ui/States";
import { useApi } from "@/hooks/useApi";
import { titleCase } from "@/lib/format";
import type { ListResponse, ProviderDescriptor } from "@/lib/types";

const PLATFORM_NAME = process.env.NEXT_PUBLIC_PLATFORM_NAME ?? "AI Agent Factory";

export default function SettingsPage() {
  const { me, loading, logout, refresh } = useAuth();
  const providers = useApi<ListResponse<ProviderDescriptor>>("/api/v1/providers");

  if (loading && !me) return <LoadingBlock rows={5} />;

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Platform"
        title="Settings"
        description="Session and organization context. Operational configuration is provided by environment variables, not edited here."
      />

      <div className="grid-2">
        <Card title="Organization">
          <dl className="kv">
            <dt>Name</dt>
            <dd>{me?.organization?.name ?? "—"}</dd>
            <dt>Organization id</dt>
            <dd className="mono">{me?.organization?.id ?? "—"}</dd>
            <dt>Your role</dt>
            <dd>
              <Badge tone="accent">{titleCase(me?.role ?? "unknown")}</Badge>
            </dd>
          </dl>
          {me?.organization?.id ? (
            <div className="row" style={{ marginTop: 14 }}>
              <CopyButton value={me.organization.id} label="Copy organization id" />
            </div>
          ) : null}
          <p className="small faint" style={{ marginTop: 12 }}>
            Renaming the organization and inviting members are not implemented in this release.
            Membership records exist in the data model so they can be added without a migration
            rewrite.
          </p>
        </Card>

        <Card title="Session">
          <dl className="kv">
            <dt>Signed in as</dt>
            <dd>{me?.user.email ?? "—"}</dd>
            <dt>User id</dt>
            <dd className="mono">{me?.user.id ?? "—"}</dd>
            <dt>Session transport</dt>
            <dd>
              httpOnly cookie <span className="mono">factory_session</span>
            </dd>
            <dt>Active tenant</dt>
            <dd>
              {me?.organization?.name ?? "—"}{" "}
              <span className="small faint">
                ({(me?.organizations?.length ?? 0) > 1
                  ? "switch from the sidebar"
                  : "single membership"})
              </span>
            </dd>
            <dt>Single sign-on</dt>
            <dd>
              {me?.sso_enabled ? (
                <Badge tone="success">OIDC configured</Badge>
              ) : (
                <Badge tone="neutral">Password login only</Badge>
              )}
            </dd>
          </dl>
          <div className="row" style={{ marginTop: 14 }}>
            <Button variant="secondary" onClick={() => void refresh()} icon={<Icon name="refresh" size={15} />}>
              Refresh session
            </Button>
            <Button variant="ghost" onClick={() => void logout()} icon={<Icon name="logout" size={15} />}>
              Sign out
            </Button>
          </div>
          <p className="small faint" style={{ marginTop: 12 }}>
            The session token is a signed JWT stored in an httpOnly cookie. It is never readable by
            browser JavaScript.
          </p>
        </Card>
      </div>

      <Card title="Roles and permissions" description="Enforced by the API, not by this UI.">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Action</th>
                <th>Owner</th>
                <th>Admin</th>
                <th>Member</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td>Create and edit agents, link providers, run tests</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
              </tr>
              <tr>
                <td>Create workspaces, model/tool connections, skills, API keys</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
                <td className="faint">No</td>
              </tr>
              <tr>
                <td>Publish and deactivate agents</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
                <td className="faint">No</td>
              </tr>
              <tr>
                <td>Read agents, runs, and provider state</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
                <td className="text-success">Yes</td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>

      <div className="grid-2">
        <Card title="Runtime configuration">
          <dl className="kv">
            <dt>Platform name</dt>
            <dd>{PLATFORM_NAME}</dd>
            <dt>Browser → API</dt>
            <dd>
              Same-origin proxy <span className="mono">/backend-api/*</span>
            </dd>
            <dt>Providers available</dt>
            <dd>
              {providers.data?.items.map((provider) => provider.name).join(", ") ?? "Loading…"}
            </dd>
          </dl>
          <p className="small faint" style={{ marginTop: 12 }}>
            Server-side values such as <span className="mono">DATABASE_URL</span>,{" "}
            <span className="mono">JWT_SECRET</span>, <span className="mono">PLATFORM_SECRETS_KEY</span>,
            and provider credentials are never exposed to this page.
          </p>
        </Card>

        <Card title="Security posture">
          <ul className="stack-sm small muted" style={{ paddingLeft: 16, listStyle: "disc" }}>
            <li>Tenant filters are applied in every resource query.</li>
            <li>Provider credentials are encrypted with a platform secret key.</li>
            <li>Customer API keys are stored as hashes and are revoked explicitly.</li>
            <li>Run payloads are stored as bounded previews, not full transcripts.</li>
            <li>
              Blocking and SSE streaming are real. Async returns an explicit
              <span className="mono"> unsupported_capability</span> because there is no queue.
            </li>
            <li>Tool and MCP headers are encrypted at rest; the UI only shows header names.</li>
          </ul>
          <p className="small faint" style={{ marginTop: 12 }}>
            No compliance certification is claimed. Backups and restore drills are documented but
            have not been validated in production.
          </p>
        </Card>
      </div>
    </div>
  );
}
