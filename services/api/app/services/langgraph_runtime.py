"""Platform-owned LangGraph runtime.

The control plane stores a small, validated DAG (see ``local_graph``) and this
module turns it into a real ``langgraph.graph.StateGraph``. Nodes execute real
LangChain chat models and real HTTP calls; nothing is simulated.

Design notes
------------
* Every node returns a partial state. ``values`` is merged, while ``steps`` and
  ``tokens`` are accumulated, which keeps branch execution observable.
* The graph is acyclic by construction, so LangGraph is used as an executor and
  state machine rather than as a persistent workflow engine.
* Models and HTTP clients are injectable so tests can run the exact same code
  path with ``FakeListChatModel`` and ``httpx.MockTransport``.
"""

from __future__ import annotations

import json
import queue
import threading
from functools import wraps
from dataclasses import dataclass, field
from typing import Annotated, Any, Callable, Iterator, TypedDict

import httpx
import operator
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.errors import AppError
from app.providers.base import ExecutionResult, StreamEvent
from app.services.local_graph import (
    GraphRuntimeError,
    evaluate_condition,
    evaluate_guardrail,
    render_template,
    render_value,
    resolve_path,
    stringify,
    template_paths,
    validate_graph,
)
from app.services.net import validate_outbound_url
from app.services.tools import call_tool_by_id


class GraphState(TypedDict, total=False):
    values: Annotated[dict[str, Any], lambda left, right: {**(left or {}), **(right or {})}]
    steps: Annotated[list[dict[str, Any]], operator.add]
    tokens: Annotated[int, operator.add]


@dataclass
class GraphRunResult:
    status: str
    output: dict[str, Any]
    values: dict[str, Any] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    token_count: int | None = None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return stringify(content)


def _usage_tokens(response: Any) -> int:
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if isinstance(total, int):
            return total
    metadata = getattr(response, "response_metadata", None)
    if isinstance(metadata, dict):
        usage = metadata.get("token_usage") or metadata.get("usage") or {}
        if isinstance(usage, dict):
            total = usage.get("total_tokens") or usage.get("total")
            if isinstance(total, int):
                return total
    return 0


def _coerce(value: Any, kind: str, field_name: str) -> Any:
    if value is None:
        return value
    if kind == "string":
        return value if isinstance(value, str) else stringify(value)
    if kind == "number":
        if isinstance(value, bool):
            raise GraphRuntimeError(f"Input '{field_name}' must be a number.")
        if isinstance(value, (int, float)):
            return value
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise GraphRuntimeError(f"Input '{field_name}' must be a number.") from exc
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.lower() in {"true", "false"}:
            return value.lower() == "true"
        raise GraphRuntimeError(f"Input '{field_name}' must be a boolean.")
    if kind == "object":
        if not isinstance(value, dict):
            raise GraphRuntimeError(f"Input '{field_name}' must be an object.")
        return value
    if kind == "array":
        if not isinstance(value, list):
            raise GraphRuntimeError(f"Input '{field_name}' must be an array.")
        return value
    return value


class TokenCallback(BaseCallbackHandler):
    """Push model tokens to a thread-safe queue for SSE consumption."""

    def __init__(self, sink: "queue.Queue[tuple[str, Any]]") -> None:
        self._sink = sink

    def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        if token:
            self._sink.put(("token", token))


class LangGraphRuntime:
    """Execute a validated graph with a real chat model and HTTP client."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str,
        base_url: str,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
        model_factory: Callable[..., Any] | None = None,
        http_client: httpx.Client | None = None,
        streaming: bool = False,
        secrets: dict[str, str] | None = None,
        allow_private_urls: bool = False,
        max_http_response_bytes: int = 2_000_000,
        settings: Settings | None = None,
        tools: dict[str, dict[str, Any]] | None = None,
        skills: dict[str, dict[str, Any]] | None = None,
        default_skill_ids: list[str] | None = None,
        tool_runner: Callable[[str, dict[str, Any]], Any] | None = None,
        retrieval: Callable[[str, str, int, float | None], dict[str, Any]] | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self._model_factory = model_factory
        self._http_client = http_client
        self.streaming = streaming
        self._secrets = dict(secrets or {})
        self._allow_private_urls = allow_private_urls
        self._max_http_response_bytes = max_http_response_bytes
        self._settings = settings
        self._tools = dict(tools or {})
        self._skills = dict(skills or {})
        self._default_skill_ids = list(default_skill_ids or [])
        self._tool_runner = tool_runner
        self._retrieval = retrieval
        self._trace: list[dict[str, Any]] = []
        # An injected client is an intentional test/replay seam. Skip DNS
        # validation there so tests stay hermetic; production has no client.
        self._validate_urls = http_client is None

    # -- model / HTTP -------------------------------------------------
    def _build_model(
        self,
        model_name: str,
        temperature: float | None,
        max_tokens: int | None,
    ) -> Any:
        if self._model_factory is not None:
            return self._model_factory(
                model=model_name,
                temperature=temperature,
                max_tokens=max_tokens,
                streaming=self.streaming,
            )
        # Imported lazily so the rest of the control plane keeps working when
        # optional LangChain dependencies are not installed.
        from langchain_openai import ChatOpenAI

        kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": self.api_key,
            "base_url": self.base_url,
        }
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if self.streaming:
            kwargs["streaming"] = True
        return ChatOpenAI(**kwargs)

    def _http(self, timeout: float) -> tuple[httpx.Client, bool]:
        if self._http_client is not None:
            return self._http_client, False
        return httpx.Client(timeout=timeout), True

    # -- context engineering ------------------------------------------
    def _history_messages(
        self, values: dict[str, Any], context: dict[str, Any]
    ) -> list[Any]:
        if not context.get("history"):
            return []
        path = str(context.get("history_path") or "history")
        raw = resolve_path(values, path)
        if not isinstance(raw, list):
            return []
        limit = int(context.get("max_history_messages") or 0)
        rows = raw[-limit:] if limit > 0 else []
        messages: list[Any] = []
        for row in rows:
            role = "user"
            content: Any = row
            if isinstance(row, dict):
                role = str(row.get("role") or "user").lower()
                content = row.get("content")
            elif isinstance(row, (list, tuple)) and len(row) == 2:
                role = str(row[0]).lower()
                content = row[1]
            text = _content_text(content).strip()
            if not text:
                continue
            if role in {"assistant", "ai", "agent"}:
                messages.append(AIMessage(content=text))
            elif role == "system":
                messages.append(SystemMessage(content=text))
            else:
                messages.append(HumanMessage(content=text))
        return messages

    @staticmethod
    def _trim_context(
        system: str,
        history: list[Any],
        prompt: str,
        max_chars: int,
    ) -> tuple[str, list[Any]]:
        """Keep the newest history first; never silently drop the user prompt."""
        budget = max(500, int(max_chars))
        total = len(system) + len(prompt) + sum(len(str(m.content)) for m in history)
        while history and total > budget:
            total -= len(str(history.pop(0).content))
        if total > budget and system:
            keep = max(0, budget - len(prompt))
            system = system[:keep]
        return system, history

    # -- node implementations ----------------------------------------
    def _input_node(self, config: dict[str, Any], raw_inputs: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            merged: dict[str, Any] = dict(raw_inputs)
            for spec in config.get("fields", []):
                name = spec["name"]
                if name in merged and merged[name] is not None:
                    merged[name] = _coerce(merged[name], spec.get("type", "string"), name)
                    continue
                default = spec.get("default")
                if default is None and spec.get("required"):
                    raise GraphRuntimeError(f"Input '{name}' is required.", node_id="input")
                merged[name] = _coerce(default, spec.get("type", "string"), name)
            merged["input"] = dict(raw_inputs)
            return {"values": merged, "steps": [{"node": "input", "type": "input"}]}

        return run

    def _llm_node(self, node_id: str, node_config: dict[str, Any]):
        def run(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
            values = state.get("values") or {}
            prompt = render_template(str(node_config.get("prompt") or ""), values)
            system = render_template(str(node_config.get("system") or ""), values).strip()
            model_name = (node_config.get("model") or self.model).strip()
            temperature = node_config.get("temperature")
            if temperature is None:
                temperature = self.default_temperature
            max_tokens = node_config.get("max_tokens")
            if max_tokens is None:
                max_tokens = self.default_max_tokens
            context = node_config.get("context") or {}
            history = self._history_messages(values, context)
            system, history = self._trim_context(
                system, history, prompt, int(context.get("max_context_chars") or 8000)
            )
            model = self._build_model(model_name, temperature, max_tokens)
            if node_config.get("response_format") == "json_object":
                model = model.bind(response_format={"type": "json_object"})
            messages: list[Any] = []
            if system:
                messages.append(SystemMessage(content=system))
            messages.extend(history)
            messages.append(HumanMessage(content=prompt))
            response = model.invoke(messages, config=config)
            text = _content_text(getattr(response, "content", response))
            tokens = _usage_tokens(response)
            output_key = node_config.get("output_key") or node_id
            step = {
                "node": node_id,
                "type": "llm",
                "model": model_name,
                "prompt": prompt[:2000],
                "output": text[:4000],
                "tokens": tokens,
            }
            return {
                "values": {output_key: text},
                "steps": [step],
                "tokens": tokens,
            }

        return run

    def _http_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            values = state.get("values") or {}
            url = render_template(str(config.get("url") or ""), values)
            if self._validate_urls:
                validate_outbound_url(
                    url,
                    allow_private=self._allow_private_urls,
                    label=f"HTTP node '{node_id}' URL",
                )
            headers: dict[str, str] = {}
            for key, value in (config.get("headers") or {}).items():
                rendered = str(value)
                for path in template_paths(rendered):
                    if path.startswith("secrets."):
                        name = path.split(".", 1)[1]
                        if name not in self._secrets:
                            raise GraphRuntimeError(
                                f"HTTP node '{node_id}' references missing secret '{name}'.",
                                node_id=node_id,
                            )
                headers[str(key)] = render_template(
                    rendered, {**values, "secrets": self._secrets}
                )
            body = render_value(config.get("body"), values)
            timeout = float(config.get("timeout_seconds") or 30)
            client, owned = self._http(timeout)
            try:
                response = client.request(
                    str(config.get("method") or "GET").upper(),
                    url,
                    headers=headers,
                    json=body if body is not None else None,
                )
            except httpx.TimeoutException as exc:
                raise GraphRuntimeError(
                    f"HTTP node '{node_id}' timed out.", node_id=node_id
                ) from exc
            except httpx.RequestError as exc:
                raise GraphRuntimeError(
                    f"HTTP node '{node_id}' could not reach the target.", node_id=node_id
                ) from exc
            finally:
                if owned:
                    client.close()
            if len(response.content) > self._max_http_response_bytes:
                raise GraphRuntimeError(
                    f"HTTP node '{node_id}' response exceeded the "
                    f"{self._max_http_response_bytes}-byte limit.",
                    node_id=node_id,
                )
            try:
                parsed: Any = response.json()
            except ValueError:
                parsed = response.text
            if response.status_code >= 400:
                raise GraphRuntimeError(
                    f"HTTP node '{node_id}' returned HTTP {response.status_code}.",
                    node_id=node_id,
                )
            output_key = config.get("output_key") or node_id
            return {
                "values": {output_key: parsed},
                "steps": [
                    {
                        "node": node_id,
                        "type": "http",
                        "method": config.get("method"),
                        "url": url,
                        "status": response.status_code,
                    }
                ],
            }

        return run

    # -- tools / agent loop -------------------------------------------
    def _tool_definition(self, tool_id: str) -> dict[str, Any]:
        tool = self._tools.get(tool_id)
        if tool is None:
            raise GraphRuntimeError(f"Tool '{tool_id}' is no longer available.")
        return tool

    def _run_tool(self, tool_id: str, arguments: dict[str, Any]) -> Any:
        if tool_id not in self._tools:
            raise GraphRuntimeError(f"Tool '{tool_id}' is not available for this run.")
        if self._tool_runner is not None:
            return self._tool_runner(tool_id, arguments)
        if self._settings is None:
            raise GraphRuntimeError("Tool execution is not configured for this runtime.")
        try:
            return call_tool_by_id(
                self._settings,
                self._tools,
                tool_id,
                arguments,
                secrets=self._secrets,
                allow_private=self._allow_private_urls,
            )
        except AppError as exc:
            raise GraphRuntimeError(exc.message) from exc

    def _openai_tool_specs(self, tool_ids: list[str]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        for tool_id in tool_ids:
            tool = self._tool_definition(tool_id)
            if not tool.get("enabled", True):
                continue
            schema = tool.get("input_schema") or {"type": "object", "properties": {}}
            specs.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool_id,
                        "description": str(
                            tool.get("description") or tool.get("name") or tool_id
                        )[:1000],
                        "parameters": schema,
                    },
                }
            )
        return specs

    def _tool_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            values = state.get("values") or {}
            tool_id = str(config.get("tool_id") or "")
            arguments = render_value(config.get("arguments") or {}, values)
            if not isinstance(arguments, dict):
                raise GraphRuntimeError(
                    f"Tool node '{node_id}' arguments must render to an object.",
                    node_id=node_id,
                )
            try:
                result = self._run_tool(tool_id, arguments)
            except GraphRuntimeError as exc:
                exc.steps = [
                    {
                        "node": node_id,
                        "type": "tool",
                        "tool_id": tool_id,
                        "arguments": arguments,
                        "error": True,
                        "output": exc.message,
                    },
                    *exc.steps,
                ]
                raise
            output_key = config.get("output_key") or node_id
            return {
                "values": {output_key: result},
                "steps": [
                    {
                        "node": node_id,
                        "type": "tool",
                        "tool_id": tool_id,
                        "arguments": arguments,
                        "output": stringify(result)[:4000],
                    }
                ],
            }

        return run

    def _agent_node(self, node_id: str, node_config: dict[str, Any]):
        def run(state: GraphState, config: RunnableConfig) -> dict[str, Any]:
            values = state.get("values") or {}
            prompt = render_template(str(node_config.get("prompt") or ""), values)
            system = render_template(str(node_config.get("system") or ""), values).strip()
            requested_skills = list(node_config.get("skill_ids") or []) + self._default_skill_ids
            skill_ids = list(
                dict.fromkeys(
                    str(item) for item in requested_skills if str(item) in self._skills
                )
            )
            if skill_ids:
                blocks = []
                for skill_id in skill_ids:
                    skill = self._skills[skill_id]
                    blocks.append(
                        f"## Skill: {skill.get('name', skill_id)}\n"
                        f"{skill.get('instructions', '')}"
                    )
                system = (system + "\n\n" + "\n\n".join(blocks)).strip()
            model_name = (node_config.get("model") or self.model).strip()
            temperature = node_config.get("temperature")
            if temperature is None:
                temperature = self.default_temperature
            max_tokens = node_config.get("max_tokens")
            if max_tokens is None:
                max_tokens = self.default_max_tokens
            max_steps = int(node_config.get("max_steps") or 6)
            tool_ids = [str(item) for item in (node_config.get("tool_ids") or [])]
            specs = self._openai_tool_specs(tool_ids)
            model = self._build_model(model_name, temperature, max_tokens)
            if specs:
                model = model.bind_tools(specs)
            context = node_config.get("context") or {}
            history = self._history_messages(values, context)
            system, history = self._trim_context(
                system, history, prompt, int(context.get("max_context_chars") or 8000)
            )
            messages: list[Any] = []
            if system:
                messages.append(SystemMessage(content=system))
            messages.extend(history)
            messages.append(HumanMessage(content=prompt))
            steps: list[dict[str, Any]] = []
            tokens = 0
            final_text = ""
            for iteration in range(1, max_steps + 1):
                response = model.invoke(messages, config=config)
                tokens += _usage_tokens(response)
                tool_calls = getattr(response, "tool_calls", None) or []
                text = _content_text(getattr(response, "content", response))
                if text.strip():
                    final_text = text
                steps.append(
                    {
                        "node": node_id,
                        "type": "agent",
                        "iteration": iteration,
                        "model": model_name,
                        "output": text[:4000],
                        "tool_calls": [call.get("name") for call in tool_calls],
                        "tokens": _usage_tokens(response),
                    }
                )
                if not tool_calls:
                    break
                messages.append(
                    AIMessage(content=text, tool_calls=tool_calls)
                )
                for call in tool_calls:
                    name = str(call.get("name") or "")
                    args = call.get("args") or {}
                    call_id = str(call.get("id") or f"call_{iteration}_{name}")
                    if name not in tool_ids:
                        raise GraphRuntimeError(
                            f"Agent node '{node_id}' requested tool '{name}', which is not attached.",
                            node_id=node_id,
                        )
                    try:
                        result = self._run_tool(name, args if isinstance(args, dict) else {})
                        body = stringify(result)
                        error = False
                    except GraphRuntimeError as exc:
                        body = exc.message
                        error = True
                    steps.append(
                        {
                            "node": node_id,
                            "type": "tool_call",
                            "tool_id": name,
                            "arguments": args,
                            "error": error,
                            "output": body[:4000],
                        }
                    )
                    messages.append(
                        ToolMessage(content=body, tool_call_id=call_id, name=name)
                    )
            else:
                final_text = final_text or "The agent reached its step limit without a final answer."
                steps.append(
                    {
                        "node": node_id,
                        "type": "agent",
                        "limit": max_steps,
                        "output": final_text[:4000],
                    }
                )
            output_key = node_config.get("output_key") or node_id
            return {
                "values": {output_key: final_text},
                "steps": steps,
                "tokens": tokens,
            }

        return run

    def _guardrail_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            decision = evaluate_guardrail(config, state.get("values") or {})
            return {
                "values": {f"__guardrail_{node_id}": decision["passed"]},
                "steps": [
                    {
                        "node": node_id,
                        "type": "guardrail",
                        "passed": decision["passed"],
                        "reasons": decision["reasons"],
                    }
                ],
            }

        return run

    def _retrieval_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            values = state.get("values") or {}
            query = render_template(str(config.get("query") or ""), values).strip()
            if not query:
                raise GraphRuntimeError(
                    f"Retrieval node '{node_id}' produced an empty query.", node_id=node_id
                )
            if self._retrieval is None:
                raise GraphRuntimeError(
                    "Knowledge retrieval is not configured for this runtime.", node_id=node_id
                )
            top_k = int(config.get("top_k") or 5)
            min_score = config.get("min_score")
            try:
                result = self._retrieval(
                    str(config.get("knowledge_base_id") or ""),
                    query,
                    top_k,
                    float(min_score) if isinstance(min_score, (int, float)) else None,
                )
            except AppError as exc:
                raise GraphRuntimeError(exc.message, node_id=node_id) from exc
            rows = result.get("results") if isinstance(result, dict) else None
            rows = rows if isinstance(rows, list) else []
            blocks = []
            for index, row in enumerate(rows, start=1):
                if not isinstance(row, dict):
                    continue
                blocks.append(
                    f"[{index}] {row.get('document_name', 'document')} "
                    f"(relevance {float(row.get('score') or 0):.2f})\n{row.get('content', '')}"
                )
            context = "\n\n".join(blocks)
            output_key = config.get("output_key") or node_id
            return {
                "values": {
                    output_key: context,
                    f"{output_key}_results": rows,
                    f"{output_key}_query": query,
                },
                "steps": [
                    {
                        "node": node_id,
                        "type": "retrieval",
                        "knowledge_base_id": config.get("knowledge_base_id"),
                        "query": query,
                        "top_k": top_k,
                        "mode": result.get("mode") if isinstance(result, dict) else None,
                        "chunks": len(rows),
                        "scores": [
                            round(float(row.get("score") or 0), 3)
                            for row in rows
                            if isinstance(row, dict)
                        ],
                    }
                ],
            }

        return run

    def _condition_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            decision = evaluate_condition(config, state.get("values") or {})
            return {
                "values": {f"__condition_{node_id}": decision},
                "steps": [{"node": node_id, "type": "condition", "result": decision}],
            }

        return run

    def _output_node(self, node_id: str, config: dict[str, Any]):
        def run(state: GraphState) -> dict[str, Any]:
            values = state.get("values") or {}
            template = str(config.get("template") or "")
            path = str(config.get("path") or "")
            if template:
                result: Any = render_template(template, values)
            elif path:
                result = resolve_path(values, path)
            else:
                result = values.get("answer", values)
            if isinstance(result, dict):
                output = dict(result)
                output.setdefault("message", stringify(result))
            else:
                output = {"message": stringify(result), "value": result}
            return {
                "values": {"_result": output},
                "steps": [{"node": node_id, "type": "output", "output": output}],
            }

        return run

    # -- execution ----------------------------------------------------
    def run(
        self,
        graph: dict[str, Any],
        inputs: dict[str, Any],
        *,
        callbacks: list[Any] | None = None,
    ) -> GraphRunResult:
        normalized = validate_graph(graph.get("nodes"), graph.get("edges"))
        self._trace = []
        app = self._compile_with_inputs(normalized, inputs)
        config: RunnableConfig = {"recursion_limit": 100}
        if callbacks:
            config["callbacks"] = callbacks
        try:
            final_state = app.invoke({"values": {}, "steps": [], "tokens": 0}, config=config)
        except GraphRuntimeError as exc:
            if not exc.steps:
                exc.steps = list(self._trace)
            raise
        except Exception as exc:  # noqa: BLE001 - normalized below
            message = str(exc) or exc.__class__.__name__
            raise GraphRuntimeError(message, steps=list(self._trace)) from exc
        values = final_state.get("values") or {}
        output = values.get("_result")
        if not isinstance(output, dict):
            output = {"message": stringify(values.get("answer", values))}
        return GraphRunResult(
            status="completed",
            output=output,
            values={key: value for key, value in values.items() if not key.startswith("_")},
            steps=final_state.get("steps") or [],
            token_count=final_state.get("tokens") or None,
        )

    def _condition_router(self, node_config: dict[str, Any]):
        def route(state: GraphState) -> str:
            return "true" if evaluate_condition(node_config, state.get("values") or {}) else "false"

        return route

    def _guardrail_router(self, node_config: dict[str, Any]):
        def route(state: GraphState) -> str:
            decision = evaluate_guardrail(node_config, state.get("values") or {})
            return "pass" if decision["passed"] else "fail"

        return route

    def _traced(self, fn: Callable[..., dict[str, Any]]):
        """Record completed steps so a failed run still explains where it stopped."""

        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
            result = fn(*args, **kwargs)
            steps = result.get("steps") if isinstance(result, dict) else None
            if isinstance(steps, list):
                self._trace.extend(steps)
            return result

        return wrapped

    def _compile_with_inputs(self, normalized: dict[str, Any], inputs: dict[str, Any]):
        """Compile with the input node bound to this request's raw values."""

        nodes = normalized["nodes"]
        edges = normalized["edges"]
        outgoing: dict[str, list[dict[str, Any]]] = {node_id: [] for node_id in nodes}
        for edge in edges:
            outgoing[edge["source"]].append(edge)

        builder: StateGraph = StateGraph(GraphState)
        for node_id, node in nodes.items():
            kind = node["type"]
            config = node.get("config") or {}
            if kind == "input":
                builder.add_node(node_id, self._traced(self._input_node(config, inputs)))
            elif kind == "llm":
                builder.add_node(node_id, self._traced(self._llm_node(node_id, config)))
            elif kind == "http":
                builder.add_node(node_id, self._traced(self._http_node(node_id, config)))
            elif kind == "condition":
                builder.add_node(node_id, self._traced(self._condition_node(node_id, config)))
            elif kind == "tool":
                builder.add_node(node_id, self._traced(self._tool_node(node_id, config)))
            elif kind == "agent":
                builder.add_node(node_id, self._traced(self._agent_node(node_id, config)))
            elif kind == "guardrail":
                builder.add_node(node_id, self._traced(self._guardrail_node(node_id, config)))
            elif kind == "retrieval":
                builder.add_node(node_id, self._traced(self._retrieval_node(node_id, config)))
            else:
                builder.add_node(node_id, self._traced(self._output_node(node_id, config)))

        input_ids = [node_id for node_id, node in nodes.items() if node["type"] == "input"]
        builder.add_edge(START, input_ids[0])
        for node_id, node in nodes.items():
            kind = node["type"]
            out = outgoing[node_id]
            if kind == "output":
                builder.add_edge(node_id, END)
            elif kind == "condition":
                mapping = {str(edge["sourceHandle"]): edge["target"] for edge in out}
                builder.add_conditional_edges(
                    node_id,
                    self._condition_router(node.get("config") or {}),
                    mapping,
                )
            elif kind == "guardrail":
                mapping = {str(edge["sourceHandle"]): edge["target"] for edge in out}
                builder.add_conditional_edges(
                    node_id,
                    self._guardrail_router(node.get("config") or {}),
                    mapping,
                )
            else:
                builder.add_edge(node_id, out[0]["target"])
        return builder.compile()

    def stream(
        self,
        graph: dict[str, Any],
        inputs: dict[str, Any],
    ) -> Iterator[StreamEvent]:
        """Execute in a worker thread and yield tokens as they arrive.

        A provider that emits token callbacks produces true incremental output.
        A provider that does not (for example a scripted fake model) still
        yields a single final chunk so clients can render the answer.
        """

        sink: queue.Queue[tuple[str, Any]] = queue.Queue()
        handler = TokenCallback(sink)

        def worker() -> None:
            try:
                result = self.run(graph, inputs, callbacks=[handler])
                sink.put(("result", result))
            except GraphRuntimeError as exc:
                sink.put(("error", exc))
            except Exception as exc:  # noqa: BLE001
                sink.put(("error", GraphRuntimeError(str(exc) or exc.__class__.__name__)))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        emitted = False
        while True:
            kind, payload = sink.get()
            if kind == "token":
                emitted = True
                yield StreamEvent.chunk(str(payload))
            elif kind == "result":
                result: GraphRunResult = payload
                if not emitted:
                    message = result.output.get("message")
                    if message:
                        yield StreamEvent.chunk(stringify(message))
                yield StreamEvent.final(
                    ExecutionResult(
                        status="completed",
                        output=result.output,
                        token_count=result.token_count,
                        provider_extension={
                            "langchain": {
                                "steps": result.steps,
                                "values": result.values,
                            }
                        },
                    )
                )
                return
            else:
                exc: GraphRuntimeError = payload
                yield StreamEvent.error(
                    exc.message, category="graph_failed"
                )
                return


def graph_from_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    """Extract the persisted graph from an AgentVersion snapshot."""

    if not snapshot:
        return None
    graph = snapshot.get("graph")
    if not isinstance(graph, dict):
        return None
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, dict) or not isinstance(edges, list):
        return None
    return {"nodes": nodes, "edges": edges}


def json_safe(value: Any) -> Any:
    """Best-effort conversion for provider extension payloads."""

    try:
        json.dumps(value, default=str)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, default=str))
