/**
 * Types and pure helpers for the platform-owned LangGraph editor.
 *
 * The shapes mirror ``services/api/app/services/local_graph.py``. The editor
 * is a client over the API: every save is validated again on the server, and
 * execution happens in the real LangGraph runtime, not in the browser.
 */

import type { IconName } from "@/components/ui/Icon";
import type { Run } from "@/lib/types";

export type LocalNodeType =
  | "input"
  | "llm"
  | "http"
  | "condition"
  | "tool"
  | "agent"
  | "guardrail"
  | "retrieval"
  | "output";

export type RouteHandle = "true" | "false" | "pass" | "fail";

export type InputFieldType = "string" | "number" | "boolean" | "object" | "array";

export type ConditionOperator =
  | "exists"
  | "not_exists"
  | "equals"
  | "not_equals"
  | "contains"
  | "not_contains"
  | "gt"
  | "gte"
  | "lt"
  | "lte"
  | "truthy"
  | "falsy"
  | "matches"
  | "in"
  | "not_in";

export type HTTPMethod = "GET" | "POST" | "PUT" | "PATCH" | "DELETE";

export interface LocalPosition {
  x: number;
  y: number;
}

export interface InputField {
  name: string;
  type: InputFieldType;
  required: boolean;
  default?: unknown;
  description?: string;
}

export interface LocalNode {
  id: string;
  type: LocalNodeType;
  name: string;
  position: LocalPosition;
  config: Record<string, unknown>;
}

export interface LocalEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: RouteHandle | null;
}

export interface LocalGraph {
  nodes: Record<string, LocalNode>;
  edges: LocalEdge[];
}

export interface LocalGraphResponse {
  provider: string;
  agent_id: string;
  revision: number;
  source: string;
  graph: LocalGraph;
  updated_at: string | null;
}

export interface LocalGraphValidation {
  valid: boolean;
  error: { message: string; node_id?: string | null } | null;
  graph: LocalGraph | null;
}

export interface LocalGraphDryRun {
  run: Run;
  revision: number;
  graph: LocalGraph | null;
}

export interface NodeMeta {
  label: string;
  description: string;
  icon: IconName;
  /** Tailwind-free CSS hook, for example ``graph-node-input``. */
  tone: string;
}

export const NODE_ORDER: LocalNodeType[] = [
  "input",
  "agent",
  "llm",
  "tool",
  "http",
  "retrieval",
  "guardrail",
  "condition",
  "output",
];

export const NODE_META: Record<LocalNodeType, NodeMeta> = {
  input: {
    label: "Input",
    description: "Declares the values a caller must send. Exactly one per graph.",
    icon: "play",
    tone: "input",
  },
  agent: {
    label: "Agent",
    description:
      "A model with tools and skills. It can call tools in a bounded loop, then answer.",
    icon: "bot",
    tone: "agent",
  },
  llm: {
    label: "LLM",
    description: "One model call. Use this for a focused transformation, not a tool loop.",
    icon: "bot",
    tone: "llm",
  },
  tool: {
    label: "Tool call",
    description: "Calls one registered HTTP or MCP tool with rendered arguments.",
    icon: "terminal",
    tone: "tool",
  },
  http: {
    label: "HTTP request",
    description: "Calls any URL directly. Prefer a registered tool when it is reusable.",
    icon: "plug",
    tone: "http",
  },
  retrieval: {
    label: "Knowledge",
    description:
      "Searches a knowledge base and returns the most relevant chunks. Put it before an LLM or agent node to ground answers.",
    icon: "database",
    tone: "retrieval",
  },
  guardrail: {
    label: "Guardrail",
    description:
      "Checks a value for blocked terms, required terms, length, or a pattern, then routes pass or fail.",
    icon: "shield",
    tone: "guardrail",
  },
  condition: {
    label: "Condition",
    description: "Routes to a true or false branch using a value path.",
    icon: "workflow",
    tone: "condition",
  },
  output: {
    label: "Output",
    description: "Returns the final message. Every branch must end here.",
    icon: "layers",
    tone: "output",
  },
};

export const INPUT_FIELD_TYPES: InputFieldType[] = [
  "string",
  "number",
  "boolean",
  "object",
  "array",
];

export const CONDITION_OPERATORS: ConditionOperator[] = [
  "truthy",
  "falsy",
  "exists",
  "not_exists",
  "equals",
  "not_equals",
  "contains",
  "not_contains",
  "gt",
  "gte",
  "lt",
  "lte",
  "matches",
  "in",
  "not_in",
];

export const HTTP_METHODS: HTTPMethod[] = ["GET", "POST", "PUT", "PATCH", "DELETE"];

/** Operators that need a comparison value on the right-hand side. */
export const VALUE_OPERATORS = new Set<ConditionOperator>([
  "equals",
  "not_equals",
  "contains",
  "not_contains",
  "gt",
  "gte",
  "lt",
  "lte",
  "matches",
  "in",
  "not_in",
]);

const ID_BASE: Record<LocalNodeType, string> = {
  input: "input",
  agent: "agent",
  llm: "llm",
  tool: "tool",
  http: "http",
  retrieval: "retrieval",
  guardrail: "guardrail",
  condition: "condition",
  output: "output",
};

export function isLocalNodeType(value: unknown): value is LocalNodeType {
  return typeof value === "string" && (NODE_ORDER as string[]).includes(value);
}

export function nextNodeId(nodes: Record<string, LocalNode>, type: LocalNodeType): string {
  const base = ID_BASE[type];
  if (!nodes[base]) return base;
  let index = 2;
  while (nodes[`${base}_${index}`]) index += 1;
  return `${base}_${index}`;
}

export function defaultValueForField(type: InputFieldType): unknown {
  if (type === "number") return 0;
  if (type === "boolean") return false;
  if (type === "object") return {};
  if (type === "array") return [];
  return "";
}

function defaultConfig(type: LocalNodeType, id: string): Record<string, unknown> {
  if (type === "input") {
    return {
      fields: [
        {
          name: "message",
          type: "string",
          required: true,
          default: null,
          description: "The caller's message.",
        },
      ],
      description: "",
    };
  }
  if (type === "agent") {
    return {
      prompt: "{{ message }}",
      system: "",
      model: null,
      temperature: 0.2,
      max_tokens: null,
      max_steps: 6,
      tool_ids: [],
      skill_ids: [],
      context: {
        history: false,
        history_path: "history",
        max_history_messages: 6,
        max_context_chars: 8000,
      },
      output_key: id,
    };
  }
  if (type === "llm") {
    return {
      prompt: "{{ message }}",
      system: "",
      model: null,
      temperature: null,
      max_tokens: null,
      context: {
        history: false,
        history_path: "history",
        max_history_messages: 6,
        max_context_chars: 8000,
      },
      response_format: "text",
      output_key: id,
    };
  }
  if (type === "tool") {
    return {
      tool_id: "",
      arguments: {},
      output_key: id,
    };
  }
  if (type === "retrieval") {
    return {
      knowledge_base_id: "",
      query: "{{ message }}",
      top_k: 5,
      min_score: null,
      output_key: id,
    };
  }
  if (type === "guardrail") {
    return {
      path: "message",
      preset: "",
      max_chars: 4000,
      min_chars: null,
      deny_terms: [],
      require_terms: [],
      pattern: "",
      pattern_mode: "deny",
      case_sensitive: false,
    };
  }
  if (type === "http") {
    return {
      method: "GET",
      url: "https://",
      headers: {},
      body: null,
      timeout_seconds: 30,
      output_key: id,
    };
  }
  if (type === "condition") {
    return { path: "message", operator: "truthy", value: null };
  }
  return { template: "", path: "message" };
}

export function createNode(
  type: LocalNodeType,
  position: LocalPosition,
  existing: Record<string, LocalNode>,
): LocalNode {
  const id = nextNodeId(existing, type);
  return {
    id,
    type,
    name: NODE_META[type].label,
    position,
    config: defaultConfig(type, id),
  };
}

export function nextEdgeId(graph: LocalGraph, source: string, target: string): string {
  const base = `e_${source}_${target}`;
  if (!graph.edges.some((edge) => edge.id === base)) return base;
  let index = 2;
  while (graph.edges.some((edge) => edge.id === `${base}_${index}`)) index += 1;
  return `${base}_${index}`;
}

/** Reject a connection that would violate the graph's single-path rules. */
export function connectionProblem(
  graph: LocalGraph,
  source: string,
  target: string,
  sourceHandle: RouteHandle | null,
): string | null {
  const sourceNode = graph.nodes[source];
  const targetNode = graph.nodes[target];
  if (!sourceNode || !targetNode) return "That connection points at a node that is not in the graph.";
  if (source === target) return "A node cannot connect to itself.";
  if (sourceNode.type === "output") return "Output nodes are terminal and cannot connect onward.";
  if (targetNode.type === "input") return "The input node cannot receive incoming connections.";

  const outgoing = graph.edges.filter((edge) => edge.source === source);
  const incoming = graph.edges.filter((edge) => edge.target === target);

  if (sourceNode.type === "condition") {
    if (sourceHandle !== "true" && sourceHandle !== "false") {
      return "Drag from the green true handle or the red false handle.";
    }
    if (outgoing.some((edge) => edge.sourceHandle === sourceHandle)) {
      return `The ${sourceHandle} branch is already connected.`;
    }
    if (outgoing.length >= 2) return "A condition node only has two branches.";
  } else if (sourceNode.type === "guardrail") {
    if (sourceHandle !== "pass" && sourceHandle !== "fail") {
      return "Drag from the pass handle or the fail handle.";
    }
    if (outgoing.some((edge) => edge.sourceHandle === sourceHandle)) {
      return `The ${sourceHandle} branch is already connected.`;
    }
    if (outgoing.length >= 2) return "A guardrail only has pass and fail branches.";
  } else {
    if (sourceHandle !== null) return "Only conditions and guardrails have labeled branches.";
    if (outgoing.length > 0) {
      const existing = graph.nodes[outgoing[0].target];
      return `This node already connects to ${existing?.name ?? "another node"}.`;
    }
  }

  if (incoming.length > 0) {
    const existing = graph.nodes[incoming[0].source];
    return `${targetNode.name} already has an incoming connection from ${
      existing?.name ?? "another node"
    }. Merges are not supported.`;
  }

  if (reaches(graph, target, source)) {
    return "That connection would create a cycle.";
  }
  return null;
}

/** True when ``from`` can reach ``to`` by following edges downstream. */
export function reaches(graph: LocalGraph, from: string, to: string): boolean {
  const seen = new Set<string>();
  const stack = [from];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    if (current === to) return true;
    if (seen.has(current)) continue;
    seen.add(current);
    for (const edge of graph.edges) {
      if (edge.source === current) stack.push(edge.target);
    }
  }
  return false;
}

/** Cheap client-side problems. The server remains the authoritative validator. */
export function localGraphProblem(graph: LocalGraph): string | null {
  const nodes = Object.values(graph.nodes);
  if (nodes.length === 0) return "Add at least one node.";
  const inputs = nodes.filter((node) => node.type === "input");
  if (inputs.length !== 1) return "A graph must contain exactly one input node.";
  if (!nodes.some((node) => node.type === "output")) {
    return "A graph must contain at least one output node.";
  }
  return null;
}

export function nodeSummary(node: LocalNode): string {
  const config = node.config;
  if (node.type === "input") {
    const fields = Array.isArray(config.fields) ? config.fields : [];
    const names = fields
      .map((field) => (field && typeof field === "object" ? String((field as InputField).name) : ""))
      .filter(Boolean);
    return names.length > 0 ? names.join(", ") : "No input fields declared";
  }
  if (node.type === "agent") {
    const model = typeof config.model === "string" && config.model ? config.model : "connection default";
    const tools = Array.isArray(config.tool_ids) ? config.tool_ids.length : 0;
    const skills = Array.isArray(config.skill_ids) ? config.skill_ids.length : 0;
    const steps = typeof config.max_steps === "number" ? config.max_steps : 6;
    return `${model} · ${tools} tools · ${skills} skills · max ${steps} steps`;
  }
  if (node.type === "tool") {
    const toolId = typeof config.tool_id === "string" && config.tool_id ? config.tool_id : "No tool selected";
    return `Tool: ${toolId}`;
  }
  if (node.type === "retrieval") {
    const base = typeof config.knowledge_base_id === "string" && config.knowledge_base_id
      ? config.knowledge_base_id
      : "No knowledge base";
    const topK = typeof config.top_k === "number" ? config.top_k : 5;
    return `${base} · top ${topK} chunks`;
  }
  if (node.type === "guardrail") {
    const path = typeof config.path === "string" ? config.path : "value";
    const preset = typeof config.preset === "string" ? config.preset : "";
    const deny = Array.isArray(config.deny_terms) ? config.deny_terms.length : 0;
    const require = Array.isArray(config.require_terms) ? config.require_terms.length : 0;
    return `${path} · ${preset ? `${preset.replace(/_/g, " ")} · ` : ""}${deny} blocked · ${require} required`;
  }
  if (node.type === "llm") {
    const model = typeof config.model === "string" && config.model ? config.model : "connection default";
    const prompt = typeof config.prompt === "string" ? config.prompt.trim() : "";
    return prompt ? `${model} · ${prompt}` : model;
  }
  if (node.type === "http") {
    const method = typeof config.method === "string" ? config.method : "GET";
    const url = typeof config.url === "string" ? config.url : "";
    return `${method} ${url}`.trim();
  }
  if (node.type === "condition") {
    const path = typeof config.path === "string" ? config.path : "";
    const operator = typeof config.operator === "string" ? config.operator : "truthy";
    return `${path || "value"} ${operator.replace(/_/g, " ")}`;
  }
  const template = typeof config.template === "string" ? config.template.trim() : "";
  const path = typeof config.path === "string" ? config.path : "";
  return template ? `Template: ${template}` : path ? `Path: ${path}` : "No output configured";
}

/** Detect the run's final shape so the console can show a useful message. */
export function runMessage(run: Run): string | null {
  const message = run.output?.message;
  if (typeof message === "string") return message;
  if (message === null || message === undefined) return null;
  try {
    return JSON.stringify(message, null, 2);
  } catch {
    return String(message);
  }
}

export interface GraphStreamEvent {
  type: "chunk" | "status" | "final" | "error" | string;
  text: string | null;
  data: Record<string, unknown>;
}
