"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { InlineError } from "@/components/ui/States";
import { useToast } from "@/components/providers/ToastProvider";
import { api, errorMessage } from "@/lib/api";
import type { Agent, AgentSettings, KnowledgeBase } from "@/lib/types";

const GUARDRAIL_OPTIONS = [
  { value: "", label: "None" },
  { value: "pii", label: "Personal data (PII)" },
  { value: "prompt_injection", label: "Prompt injection" },
  { value: "json_object", label: "Require a JSON object" },
  { value: "safe_text", label: "Safe text (control chars / markup)" },
];

function numberOrUndefined(value: string): number | undefined {
  if (!value.trim()) return undefined;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export function AgentSettingsCard({
  agent,
  connectionId,
  knowledgeBases,
  onSaved,
}: {
  agent: Agent;
  connectionId: string | null;
  knowledgeBases: KnowledgeBase[];
  onSaved: () => void;
}) {
  const toast = useToast();
  const initial = useMemo<AgentSettings>(() => agent.settings ?? {}, [agent.settings]);
  const [model, setModel] = useState(initial.model ?? "");
  const [temperature, setTemperature] = useState(
    initial.temperature != null ? String(initial.temperature) : "",
  );
  const [maxTokens, setMaxTokens] = useState(
    initial.max_tokens != null ? String(initial.max_tokens) : "",
  );
  const [contextTokens, setContextTokens] = useState(
    initial.context_window_tokens != null ? String(initial.context_window_tokens) : "",
  );
  const [historyMessages, setHistoryMessages] = useState(
    initial.max_history_messages != null ? String(initial.max_history_messages) : "",
  );
  const [inputGuardrail, setInputGuardrail] = useState(initial.guardrail_input ?? "");
  const [outputGuardrail, setOutputGuardrail] = useState(initial.guardrail_output ?? "");
  const [denyTerms, setDenyTerms] = useState((initial.deny_terms ?? []).join(", "));
  const [kbIds, setKbIds] = useState<string[]>(initial.knowledge_base_ids ?? []);
  const [ragTopK, setRagTopK] = useState(
    initial.rag_top_k != null ? String(initial.rag_top_k) : "",
  );
  const [ragMinScore, setRagMinScore] = useState(
    initial.rag_min_score != null ? String(initial.rag_min_score) : "",
  );
  const [systemPrompt, setSystemPrompt] = useState(initial.system_prompt ?? "");
  const [models, setModels] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setModel(initial.model ?? "");
    setTemperature(initial.temperature != null ? String(initial.temperature) : "");
    setMaxTokens(initial.max_tokens != null ? String(initial.max_tokens) : "");
    setContextTokens(
      initial.context_window_tokens != null ? String(initial.context_window_tokens) : "",
    );
    setHistoryMessages(
      initial.max_history_messages != null ? String(initial.max_history_messages) : "",
    );
    setInputGuardrail(initial.guardrail_input ?? "");
    setOutputGuardrail(initial.guardrail_output ?? "");
    setDenyTerms((initial.deny_terms ?? []).join(", "));
    setKbIds(initial.knowledge_base_ids ?? []);
    setRagTopK(initial.rag_top_k != null ? String(initial.rag_top_k) : "");
    setRagMinScore(initial.rag_min_score != null ? String(initial.rag_min_score) : "");
    setSystemPrompt(initial.system_prompt ?? "");
  }, [initial]);

  useEffect(() => {
    if (!connectionId) {
      setModels([]);
      return;
    }
    let active = true;
    api
      .get<{ models: string[] }>(`/api/v1/provider-connections/${connectionId}/models`)
      .then((data) => {
        if (active) setModels(data.models ?? []);
      })
      .catch(() => {
        // Model discovery is a convenience; a text value still saves.
      });
    return () => {
      active = false;
    };
  }, [connectionId]);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const settings: AgentSettings = {
      model: model.trim() || undefined,
      temperature: numberOrUndefined(temperature),
      max_tokens: numberOrUndefined(maxTokens),
      context_window_tokens: numberOrUndefined(contextTokens),
      max_history_messages: numberOrUndefined(historyMessages),
      guardrail_input: inputGuardrail || undefined,
      guardrail_output: outputGuardrail || undefined,
      deny_terms: denyTerms
        .split(",")
        .map((term) => term.trim())
        .filter(Boolean),
      knowledge_base_ids: kbIds,
      rag_top_k: numberOrUndefined(ragTopK),
      rag_min_score: numberOrUndefined(ragMinScore),
      system_prompt: systemPrompt.trim() || undefined,
    };
    try {
      await api.patch<Agent>(`/api/v1/agents/${agent.id}`, { settings });
      toast.push("Agent settings saved.", "success");
      onSaved();
    } catch (cause) {
      setError(errorMessage(cause));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card
      title="Agent settings"
      description="Applied to every model call in this agent. Node values override these defaults; knowledge is retrieved before each LLM or agent step."
    >
      <form className="stack" onSubmit={save} noValidate>
        {error ? <InlineError message={error} /> : null}

        <div className="form-grid">
          <Field
            label="Default model"
            htmlFor="agent-model"
            hint="Overrides the connection model. Leave empty to use the connection default."
          >
            <Input
              id="agent-model"
              list="agent-model-options"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              placeholder="openrouter/auto"
              maxLength={200}
            />
            <datalist id="agent-model-options">
              {models.map((name) => (
                <option key={name} value={name} />
              ))}
            </datalist>
          </Field>

          <Field label="Temperature" htmlFor="agent-temperature" hint="0 = deterministic, 2 = creative.">
            <Input
              id="agent-temperature"
              type="number"
              min={0}
              max={2}
              step="0.1"
              value={temperature}
              onChange={(event) => setTemperature(event.target.value)}
              placeholder="0.4"
            />
          </Field>

          <Field label="Max output tokens" htmlFor="agent-max-tokens">
            <Input
              id="agent-max-tokens"
              type="number"
              min={1}
              max={32000}
              value={maxTokens}
              onChange={(event) => setMaxTokens(event.target.value)}
              placeholder="800"
            />
          </Field>

          <Field
            label="Context window (tokens)"
            htmlFor="agent-context-tokens"
            hint="History and retrieved chunks are trimmed to fit (~4 chars per token)."
          >
            <Input
              id="agent-context-tokens"
              type="number"
              min={512}
              max={200000}
              step={512}
              value={contextTokens}
              onChange={(event) => setContextTokens(event.target.value)}
              placeholder="8192"
            />
          </Field>

          <Field label="History messages" htmlFor="agent-history">
            <Input
              id="agent-history"
              type="number"
              min={0}
              max={50}
              value={historyMessages}
              onChange={(event) => setHistoryMessages(event.target.value)}
              placeholder="0"
            />
          </Field>

          <Field label="Input guardrail" htmlFor="agent-guardrail-input">
            <Select
              id="agent-guardrail-input"
              value={inputGuardrail}
              onChange={(event) => setInputGuardrail(event.target.value)}
            >
              {GUARDRAIL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field label="Output guardrail" htmlFor="agent-guardrail-output">
            <Select
              id="agent-guardrail-output"
              value={outputGuardrail}
              onChange={(event) => setOutputGuardrail(event.target.value)}
            >
              {GUARDRAIL_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </Select>
          </Field>

          <Field
            label="Blocked terms"
            htmlFor="agent-deny-terms"
            hint="Comma separated. Applied by both guardrails."
          >
            <Input
              id="agent-deny-terms"
              value={denyTerms}
              onChange={(event) => setDenyTerms(event.target.value)}
              placeholder="competitor, internal-only"
            />
          </Field>

          <div className="span-2">
            <Field label="System prompt" htmlFor="agent-system-prompt" hint="Prepended to every LLM and agent node.">
              <Textarea
                id="agent-system-prompt"
                rows={3}
                value={systemPrompt}
                onChange={(event) => setSystemPrompt(event.target.value)}
                placeholder="You are a concise assistant for…"
                maxLength={8000}
              />
            </Field>
          </div>

          <div className="span-2">
            <span className="field-label">Knowledge bases (RAG)</span>
            {knowledgeBases.length === 0 ? (
              <p className="small faint">
                No knowledge base yet. <Link href="/knowledge">Create one</Link> to ground answers.
              </p>
            ) : (
              <div className="graph-check-list">
                {knowledgeBases.map((base) => (
                  <label className="checkbox-row" key={base.id}>
                    <input
                      type="checkbox"
                      checked={kbIds.includes(base.id)}
                      onChange={(event) =>
                        setKbIds((current) =>
                          event.target.checked
                            ? [...current, base.id]
                            : current.filter((id) => id !== base.id),
                        )
                      }
                    />
                    <span>
                      <strong>{base.name}</strong>{" "}
                      <span className="small faint">
                        {base.mode === "vector"
                          ? `embeddings · ${base.embedding_model ?? "no model"}`
                          : "keyword"}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            )}
            <p className="small faint" style={{ marginTop: 8 }}>
              Vector knowledge bases use their own embedding connection and model
              (configure them in Knowledge). Keyword bases need no embeddings.
            </p>
          </div>

          <Field label="RAG top-k" htmlFor="agent-rag-top-k">
            <Input
              id="agent-rag-top-k"
              type="number"
              min={1}
              max={20}
              value={ragTopK}
              onChange={(event) => setRagTopK(event.target.value)}
              placeholder="4"
            />
          </Field>

          <Field label="RAG minimum score" htmlFor="agent-rag-score" hint="0 to 1; leave empty for no floor.">
            <Input
              id="agent-rag-score"
              type="number"
              min={0}
              max={1}
              step="0.05"
              value={ragMinScore}
              onChange={(event) => setRagMinScore(event.target.value)}
              placeholder="0.2"
            />
          </Field>
        </div>

        <div className="row">
          <Button type="submit" loading={busy}>
            Save agent settings
          </Button>
          <span className="small faint">
            Guardrails block the run before the model (input) or after the graph (output).
          </span>
        </div>
      </form>
    </Card>
  );
}
