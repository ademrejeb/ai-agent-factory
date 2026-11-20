export interface ErrorHelp {
  title: string;
  why: string;
  fix: string;
  tone: "danger" | "warning" | "neutral";
}

/**
 * Plain-language explanations for every error category the platform emits.
 * Unknown codes are domain references from a connected system, not platform
 * codes, and are described as such instead of pretending to know them.
 */
const CATALOG: Record<string, ErrorHelp> = {
  provider_unreachable: {
    title: "The model endpoint did not answer",
    why: "The platform could not reach the OpenAI-compatible endpoint, or /models returned an error.",
    fix: "Check that Ollama (or your gateway) is running, the base URL usually ends in /v1, and the API key is valid.",
    tone: "danger",
  },
  invalid_graph: {
    title: "The agent graph is not valid",
    why: "A required node, connection, or field is missing, or a branch does not end at an output.",
    fix: "Open the graph editor, run Validate, and fix the node named in the message. Save and run again.",
    tone: "danger",
  },
  graph_failed: {
    title: "The graph stopped while running",
    why: "A node failed — usually a model call, an HTTP tool, a guardrail, or a tool-calling loop.",
    fix: "Open the run's provider extension to see which node failed. Test that tool separately before retrying.",
    tone: "danger",
  },
  tool_failed: {
    title: "A connected tool returned an error",
    why: "The tool endpoint answered with a non-2xx status, or an MCP server returned a JSON-RPC error.",
    fix: "Open Tools, test the tool with the same arguments, and fix the URL, authorization header, or remote arguments.",
    tone: "danger",
  },
  tool_timeout: {
    title: "A tool took too long",
    why: "The external endpoint did not answer inside the configured timeout.",
    fix: "Raise the tool timeout if the endpoint is legitimately slow, or make the endpoint faster.",
    tone: "warning",
  },
  tool_unreachable: {
    title: "A tool could not be reached",
    why: "DNS, TLS, or the network blocked the outbound call from the API.",
    fix: "Verify the URL from the API host, not just your laptop, and check the allow-private setting.",
    tone: "danger",
  },
  invalid_lifecycle: {
    title: "This action is not available yet",
    why: "The agent has not reached a lifecycle step that allows this action.",
    fix: "Link a model connection, run a successful test, then publish before calling the gateway.",
    tone: "warning",
  },
  not_published: {
    title: "No live version yet",
    why: "Gateway calls only use a published snapshot; the draft is not live.",
    fix: "Run a successful test and publish the agent. Then retry with a customer key.",
    tone: "warning",
  },
  unsupported_capability: {
    title: "This runtime does not support that mode",
    why: "The platform runtime supports blocking and streaming runs, but not an external async queue.",
    fix: "Use the blocking or streaming test console. There is no queued run to poll.",
    tone: "neutral",
  },
  client_cancelled: {
    title: "The caller closed the stream",
    why: "The browser or gateway connection ended before the model finished.",
    fix: "This is not a model failure. Retry if the answer is still needed; the provider may have completed the work.",
    tone: "warning",
  },
  rate_limited: {
    title: "Too many requests",
    why: "A per-key or per-IP rate limit was reached.",
    fix: "Wait for the window to reset, or raise the configured limit for this environment.",
    tone: "warning",
  },
  forbidden: {
    title: "Your role cannot do that",
    why: "The active tenant membership does not have permission for this action.",
    fix: "Ask a tenant owner or admin, or switch tenant from the top bar.",
    tone: "warning",
  },
  unauthorized: {
    title: "Your session is no longer valid",
    why: "The session cookie expired, was revoked, or belongs to another origin.",
    fix: "Sign in again. SSO users should use the SSO button so the session is reissued by this app.",
    tone: "warning",
  },
  sso_unavailable: {
    title: "Single sign-on is unavailable",
    why: "The identity provider discovery or token endpoint did not answer.",
    fix: "Check SSO_ISSUER and client settings, then retry. Password login still works.",
    tone: "danger",
  },
};

export function explainError(code: string | null | undefined, message?: string | null): ErrorHelp {
  if (code && CATALOG[code]) return CATALOG[code];
  if (code && /^[A-Z]{1,4}-?\d{1,5}$/.test(code)) {
    return {
      title: `${code} is a domain reference`,
      why: `${code} comes from the connected business system, not from this platform. It identifies a specific failure record there.`,
      fix: `Open the source record for ${code} to read its causes and repair steps. The platform can send its context to an agent, but it cannot invent the meaning of that reference.`,
      tone: "neutral",
    };
  }
  return {
    title: code ? code.replace(/_/g, " ") : "Run failed",
    why: message || "The provider reported a failure without a normalized category.",
    fix: "Open the run's provider extension for the failing node or step, then retry after correcting it.",
    tone: "danger",
  };
}
