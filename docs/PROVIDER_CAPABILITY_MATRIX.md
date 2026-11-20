# Runtime capability matrix

Only one runtime remains. Dify and Sim were removed because their APIs could not be
configured end to end here (no graph authoring for Dify; no workflow creation for Sim).
Keeping their screens would advertise capabilities this repository does not implement.

| Capability | Platform runtime |
| --- | --- |
| Model endpoint | Any OpenAI-compatible `GET /models` + chat endpoint |
| Ollama / LM Studio / vLLM / LiteLLM | Verified path |
| Graph authoring | Yes, platform-owned |
| Blocking execution | Yes |
| SSE streaming | Yes, token-level when the endpoint streams |
| Async execution | No; explicit `unsupported_capability` |
| Run lookup | Platform records, not provider polling |
| Tools | HTTP tools and MCP tools (JSON-RPC over HTTP) |
| Agent tool loop | Yes, bounded by `max_steps` (max 12) |
| Skills | Yes |
| Guardrails | Yes, pass/fail branches |
| Merges / arbitrary cycles | No |
| Stdio MCP | No; HTTP bridge required |
| Provider-side authoring | N/A; the platform owns the graph |
