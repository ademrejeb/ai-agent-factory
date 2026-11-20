export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(message: string, code: string, status: number, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

interface ErrorBody {
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
  detail?: unknown;
}

const API_BASE = "/backend-api";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers,
      credentials: "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "The control plane is unreachable. Check that the API is running.",
      "network_error",
      0,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const text = await response.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = null;
    }
  }

  if (!response.ok) {
    const parsed = (body ?? {}) as ErrorBody;
    const message =
      parsed.error?.message ??
      (typeof parsed.detail === "string" ? parsed.detail : null) ??
      `Request failed with HTTP ${response.status}.`;
    throw new ApiError(
      message,
      parsed.error?.code ?? "request_failed",
      response.status,
      parsed.error?.details ?? {},
    );
  }

  return body as T;
}

export const api = {
  get<T>(path: string): Promise<T> {
    return request<T>(path);
  },
  post<T>(path: string, body?: unknown): Promise<T> {
    return request<T>(path, {
      method: "POST",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  },
  patch<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, { method: "PATCH", body: JSON.stringify(body) });
  },
  put<T>(path: string, body: unknown): Promise<T> {
    return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
  },
  del<T>(path: string): Promise<T> {
    return request<T>(path, { method: "DELETE" });
  },
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export interface StreamEventPayload {
  type: string;
  text: string | null;
  data: Record<string, unknown>;
}

interface StreamOptions {
  signal?: AbortSignal;
  onEvent: (event: StreamEventPayload) => void;
}

function parseStreamBlock(block: string): StreamEventPayload | null {
  let eventName = "";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      eventName = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).replace(/^ /, ""));
    }
  }
  if (dataLines.length === 0) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(dataLines.join("\n"));
  } catch {
    return null;
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return null;
  const body = parsed as { type?: unknown; text?: unknown; data?: unknown };
  return {
    type: eventName || (typeof body.type === "string" ? body.type : "message"),
    text: typeof body.text === "string" ? body.text : null,
    data:
      body.data && typeof body.data === "object" && !Array.isArray(body.data)
        ? (body.data as Record<string, unknown>)
        : {},
  };
}

/**
 * POST a JSON body and consume a Server-Sent Events response.
 *
 * ``fetch`` is used instead of ``EventSource`` because the platform routes are
 * authenticated POSTs. Aborting the supplied signal closes the stream and
 * lets the browser drop the connection.
 */
export async function streamRequest(
  path: string,
  body: unknown,
  { signal, onEvent }: StreamOptions,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      credentials: "include",
      cache: "no-store",
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(
      "The control plane is unreachable. Check that the API is running.",
      "network_error",
      0,
    );
  }

  if (!response.ok) {
    const text = await response.text();
    let parsed: ErrorBody = {};
    try {
      parsed = text ? (JSON.parse(text) as ErrorBody) : {};
    } catch {
      parsed = {};
    }
    throw new ApiError(
      parsed.error?.message ?? `Streaming request failed with HTTP ${response.status}.`,
      parsed.error?.code ?? "request_failed",
      response.status,
      parsed.error?.details ?? {},
    );
  }
  if (!response.body) {
    throw new ApiError(
      "This browser cannot read streaming responses.",
      "stream_unsupported",
      0,
    );
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const event = parseStreamBlock(block);
      if (event) onEvent(event);
      boundary = buffer.indexOf("\n\n");
    }
  }
  buffer += decoder.decode().replace(/\r\n/g, "\n");
  if (buffer.trim()) {
    const event = parseStreamBlock(buffer);
    if (event) onEvent(event);
  }
}
