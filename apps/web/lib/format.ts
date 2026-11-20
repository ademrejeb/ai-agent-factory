export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

const CAPABILITY_LABELS: Record<string, string> = {
  execute: "Execution",
  blocking: "Blocking calls",
  streaming: "Streaming",
  async: "Async runs",
  graph: "Graph execution",
  tools: "Tools",
  http_mcp: "HTTP / MCP",
  agent_loop: "Agent tool loop",
  guardrails: "Guardrails",
  run_lookup: "Run lookup",
  resource_creation: "Resource creation",
  resource_listing: "Resource listing",
  visual_authoring: "Visual authoring",
  block_catalog: "Block catalog",
  deploy: "Deploy",
  info: "App info",
  mode: "App mode",
  streaming_only_modes: "Streaming-only modes",
};

const CAPABILITY_VALUES: Record<string, string> = {
  verified: "Verified",
  verified_workflow_only: "Workflow runs only",
  verified_not_implemented: "API verified, not wired",
  unsupported: "Not supported",
  adapter_not_implemented: "Not wired",
  personal_key_required: "Personal API key required",
  single_app_scope: "Single app",
  true: "Supported",
  false: "Not supported",
};

export function capabilityLabel(key: string): string {
  return CAPABILITY_LABELS[key] ?? titleCase(key);
}

export function capabilityValue(value: unknown): string {
  const raw = String(value);
  return CAPABILITY_VALUES[raw] ?? titleCase(raw);
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatRelative(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const seconds = Math.round((date.getTime() - Date.now()) / 1000);
  const absolute = Math.abs(seconds);
  const formatter = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  if (absolute < 60) return formatter.format(seconds, "second");
  if (absolute < 3600) return formatter.format(Math.round(seconds / 60), "minute");
  if (absolute < 86400) return formatter.format(Math.round(seconds / 3600), "hour");
  return formatter.format(Math.round(seconds / 86400), "day");
}

export function formatDuration(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined) return "—";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  if (milliseconds < 60_000) return `${(milliseconds / 1000).toFixed(2)} s`;
  return `${(milliseconds / 60_000).toFixed(1)} min`;
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat().format(value);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatBytes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

export function truncate(value: string, max = 120): string {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

export function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  const index = value.indexOf("_");
  if (index === -1) return value.length > 14 ? `${value.slice(0, 12)}…` : value;
  return `${value.slice(0, index + 5)}…${value.slice(-6)}`;
}

export function jsonPreview(value: unknown, max = 4000): string {
  try {
    return JSON.stringify(value, null, 2)?.slice(0, max) ?? "—";
  } catch {
    return String(value);
  }
}

export function providerConsoleUrl(baseUrl: string): string {
  try {
    const url = new URL(baseUrl);
    url.pathname = url.pathname.replace(/\/v1\/?$/, "");
    return url.toString().replace(/\/$/, "");
  } catch {
    return baseUrl;
  }
}
