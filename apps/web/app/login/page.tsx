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

function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/overview";
  return value;
}

export default function LoginPage() {
  const { me, loading, refresh } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sso, setSso] = useState<{ enabled: boolean; label: string }>({
    enabled: false,
    label: "Continue with SSO",
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ssoError = params.get("sso_error");
    if (ssoError) setError(ssoError);
    api
      .get<{ enabled: boolean; label: string; button_label?: string }>(
        "/api/v1/auth/sso/config",
      )
      .then((config) =>
        setSso({ enabled: config.enabled, label: config.button_label ?? config.label }),
      )
      .catch(() => setSso({ enabled: false, label: "Continue with SSO" }));
  }, []);

  useEffect(() => {
    if (!loading && me) {
      const next = safeNext(new URLSearchParams(window.location.search).get("next"));
      window.location.replace(next);
    }
  }, [loading, me]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.post("/api/v1/auth/login", { email, password });
      await refresh();
      const next = safeNext(new URLSearchParams(window.location.search).get("next"));
      window.location.replace(next);
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
          <h1 className="auth-title">Sign in</h1>
          <p className="auth-subtitle">Access the agent control plane for your organization.</p>

          <form className="auth-form" onSubmit={onSubmit} noValidate>
            {error ? <InlineError message={error} /> : null}
            <Field label="Work email" htmlFor="email" required>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@company.com"
                required
                autoFocus
              />
            </Field>
            <Field label="Password" htmlFor="password" required>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
              />
            </Field>
            <Button type="submit" loading={busy} disabled={!email || !password}>
              Sign in
            </Button>
          </form>

          {sso.enabled ? (
            <a className="btn btn-secondary btn-md auth-sso" href="/backend-api/api/v1/auth/sso/start">
              <Icon name="shield" size={15} />
              <span>{sso.label}</span>
            </a>
          ) : null}

          <p className="auth-footer">
            No account yet? <Link href="/register">Create an organization</Link>
          </p>
        </div>
      </div>

      <aside className="auth-aside">
        <div className="auth-aside-inner">
          <p className="auth-kicker">Agent control plane</p>
          <h2 className="auth-headline">
            Build, test, and run agents on your own model endpoint.
          </h2>
          <p className="auth-copy">
            Connect Ollama or any OpenAI-compatible endpoint, compose tools, MCP servers, skills,
            and guardrails in a real graph, then expose the published result through a scoped
            customer API.
          </p>
          <ul className="auth-points">
            <li>
              <Icon name="shield" size={16} />
              <span>Tenant isolation enforced server-side, not by the browser.</span>
            </li>
            <li>
              <Icon name="key" size={16} />
              <span>Provider credentials stay encrypted and never return to the UI.</span>
            </li>
            <li>
              <Icon name="play" size={16} />
              <span>Every test and gateway call is recorded as a platform run.</span>
            </li>
          </ul>
          <p className="auth-note">
            Password login and in-app OIDC SSO both issue this app&apos;s own cookie. Tenants are
            selected in the app; you are not redirected to a separate identity portal to work.
          </p>
        </div>
      </aside>
    </div>
  );
}
