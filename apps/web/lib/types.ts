export type LifecycleStatus =
  | "draft"
  | "configured"
  | "tested"
  | "validated"
  | "published"
  | "monitored"
  | "failed"
  | "deactivated";

export interface User {
  id: string;
  email: string;
}

export interface Organization {
  id: string;
  name: string;
}

export interface OrganizationSummary extends Organization {
  slug?: string;
  role: "owner" | "admin" | "member" | "viewer";
}

export interface Me {
  user: User;
  organization: Organization | null;
  role: "owner" | "admin" | "member" | null;
  organizations?: OrganizationSummary[];
  sso_enabled?: boolean;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  kind: "experiment" | "production" | string;
  organization_id: string;
  created_at: string;
}

export interface Deployment {
  id: string;
  status: string;
  health_status: string;
  environment: string;
  last_health_check_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface Agent {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  purpose: string;
  tags: string[];
  skill_ids: string[];
  lifecycle_status: LifecycleStatus;
  provider: string | null;
  provider_connection_id: string | null;
  provider_resource_id: string | null;
  provider_resource_kind: string | null;
  last_sync_error: string | null;
  archived_at: string | null;
  deployment: Deployment | null;
  created_at: string;
}

export interface ProviderCapabilities {
  [key: string]: string | number | boolean | null;
}

export interface ProviderDescriptor {
  id: string;
  name: string;
  summary: string;
  setup: string;
  base_url_placeholder: string;
  base_url_help: string;
  auth_field: string;
  auth_label: string;
  requires_workspace_id: boolean;
  requires_model: boolean;
  resource_kind: string;
  docs_url: string;
  capabilities: ProviderCapabilities;
  limitations: string[];
}

export interface ProviderConnection {
  id: string;
  name: string;
  provider: string;
  base_url: string;
  status: string;
  last_error: string | null;
  last_checked_at: string | null;
  capabilities: Record<string, unknown>;
  extra_config: Record<string, unknown>;
  has_credentials: boolean;
  created_at: string;
}

export interface ProviderResource {
  id: string | null;
  name: string;
  kind?: string | null;
  description?: string;
  deployed?: boolean;
}

export interface Run {
  run_id: string;
  agent_id: string;
  agent_name: string | null;
  deployment_id: string | null;
  status: string;
  source: string;
  provider: string | null;
  provider_run_id: string | null;
  correlation_id: string;
  input: { bytes?: number; preview?: string; truncated?: boolean };
  output: {
    bytes?: number;
    preview?: string;
    truncated?: boolean;
    message?: unknown;
    conversation_id?: string | null;
    provider_extension?: Record<string, unknown>;
  };
  error_category: string | null;
  error_message: string | null;
  duration_ms: number | null;
  token_count: number | null;
  token_count_is_estimate: boolean;
  started_at: string;
  completed_at: string | null;
}

export interface RunPage {
  items: Run[];
  total: number;
  limit: number;
  offset: number;
}

export interface AgentVersion {
  id: string;
  agent_id: string;
  version: number;
  snapshot: Record<string, unknown>;
  created_at: string;
}

export interface ApiCredential {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  revoked_at: string | null;
  last_used_at: string | null;
  created_at: string;
  secret?: string;
  warning?: string;
}

export interface OverviewDay {
  date: string;
  completed: number;
  failed: number;
  other: number;
}

export interface Overview {
  generated_at: string;
  window_days: number;
  counts: {
    agents_total: number;
    agents_published: number;
    agents_needs_attention: number;
    provider_connections: number;
    provider_connected: number;
    runs_total: number;
    runs_completed: number;
    runs_failed: number;
    success_rate: number | null;
    avg_latency_ms: number | null;
    p50_latency_ms: number | null;
    p95_latency_ms: number | null;
    tokens_reported: number;
    tokens_estimated: number;
  };
  runs_by_day: OverviewDay[];
  top_agents: Array<{ agent_id: string; name: string; runs: number; failed: number }>;
  recent_runs: Run[];
  recent_failures: Run[];
  attention: Array<{
    agent_id: string;
    name: string;
    reason: string;
    lifecycle_status: LifecycleStatus;
  }>;
  provider_connections: ProviderConnection[];
}

export interface AgentSecret {
  name: string;
  updated_at: string;
  present: boolean;
}

export interface Tool {
  id: string;
  name: string;
  kind: "http" | "mcp";
  description: string;
  config: Record<string, unknown>;
  input_schema: Record<string, unknown>;
  headers_configured: string[];
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  instructions: string;
  created_at: string;
  updated_at: string;
}

export interface McpTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ListResponse<T> {
  items: T[];
}
