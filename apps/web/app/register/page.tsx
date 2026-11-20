"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { useAuth } from "@/components/providers/AuthProvider";
import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { Logo } from "@/components/ui/Logo";
import { InlineError } from "@/components/ui/States";
import { api, errorMessage } from "@/lib/api";

const PLATFORM_NAME = process.env.NEXT_PUBLIC_PLATFORM_NAME ?? "AI Agent Factory";

export default function RegisterPage() {
  const { me, loading, refresh } = useAuth();
  const [organization, setOrganization] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loading && me) window.location.replace("/overview");
  }, [loading, me]);

  const mismatch = confirm.length > 0 && confirm !== password;
  const tooShort = password.length > 0 && password.length < 10;
  const valid =
    organization.trim().length >= 2 && email.trim().length > 0 && password.length >= 10 && !mismatch;

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/auth/register", {
        organization_name: organization.trim(),
        email: email.trim(),
        password,
      });
      await refresh();
      window.location.replace("/overview");
    } catch (err) {
      setError(errorMessage(err));
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-panel">
        <div className="auth-card">
          <Link href="/" className="auth-brand">
            <Logo size={30} />
            <span className="brand-inline-name">{PLATFORM_NAME}</span>
          </Link>
          <h1 className="auth-title">Create your organization</h1>
          <p className="auth-subtitle">
            You will be the owner of a new tenant with a default workspace.
          </p>

          <form className="auth-form" onSubmit={onSubmit} noValidate>
            {error ? <InlineError message={error} /> : null}
            <Field
              label="Organization name"
              htmlFor="organization"
              hint="Used for your tenant. The URL slug is generated automatically."
              required
            >
              <Input
                id="organization"
                value={organization}
                onChange={(event) => setOrganization(event.target.value)}
                placeholder="Acme Labs"
                required
                autoFocus
              />
            </Field>
            <Field label="Work email" htmlFor="email" required>
              <Input
                id="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
              />
            </Field>
            <Field
              label="Password"
              htmlFor="password"
              hint="At least 10 characters."
              error={tooShort ? "Password must be at least 10 characters." : null}
              required
            >
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </Field>
            <Field
              label="Confirm password"
              htmlFor="confirm"
              error={mismatch ? "Passwords do not match." : null}
              required
            >
              <Input
                id="confirm"
                type="password"
                autoComplete="new-password"
                value={confirm}
                onChange={(event) => setConfirm(event.target.value)}
                required
              />
            </Field>
            <Button type="submit" loading={busy} disabled={!valid}>
              Create organization
            </Button>
          </form>

          <p className="auth-footer">
            Already have an account? <Link href="/login">Sign in</Link>
          </p>
        </div>
      </div>

      <aside className="auth-aside">
        <div className="auth-aside-inner">
          <p className="auth-kicker">Start with the real thing</p>
          <h2 className="auth-headline">Start with the model you already run.</h2>
          <p className="auth-copy">
            Connect local Ollama or any OpenAI-compatible endpoint. Build a real agent graph with
            tools, MCP servers, skills, and guardrails, then make it callable through one gateway.
          </p>
          <ul className="auth-points">
            <li>
              <Icon name="plug" size={16} />
              <span>Model and tool credentials are encrypted server-side only.</span>
            </li>
            <li>
              <Icon name="layers" size={16} />
              <span>Tenants are isolated server-side; switching happens inside the app.</span>
            </li>
            <li>
              <Icon name="terminal" size={16} />
              <span>Issue scoped customer keys and call one stable API contract.</span>
            </li>
          </ul>
          <p className="auth-note">
            OIDC SSO is available when the deployment configures it. Password login stays
            available, and SSO never sends you to a separate product portal to work.
          </p>
        </div>
      </aside>
    </div>
  );
}
