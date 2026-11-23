"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { useApi } from "@/hooks/useApi";
import {
  CONDITION_OPERATORS,
  HTTP_METHODS,
  INPUT_FIELD_TYPES,
  NODE_META,
  VALUE_OPERATORS,
  defaultValueForField,
  type ConditionOperator,
  type InputField,
  type InputFieldType,
  type LocalNode,
} from "@/lib/local-graph";
import type { KnowledgeBase, ListResponse, Skill, Tool } from "@/lib/types";

interface LocalGraphInspectorProps {
  node: LocalNode | null;
  readOnly: boolean;
  availableValues: string[];
  onChange: (node: LocalNode) => void;
  onDelete: (nodeId: string) => void;
  onClose?: () => void;
}

export function LocalGraphInspector(props: LocalGraphInspectorProps) {
  const { node } = props;
  if (!node) {
    return (
      <aside className="wf-panel wf-inspector" aria-label="Node inspector">
        <header className="wf-panel-head">
          <div>
            <h2>Inspector</h2>
            <p>Select a node on the canvas.</p>
          </div>
        </header>
        <div className="wf-inspector-empty">
          <span className="empty-icon">
            <Icon name="workflow" size={20} />
          </span>
          <p className="small muted">
            Node configuration appears here. Prompt templates can reference input values and upstream
            outputs with <span className="mono">{"{{ value }}"}</span>.
          </p>
        </div>
      </aside>
    );
  }
  return <InspectorBody key={node.id} {...props} node={node} />;
}

function InspectorBody({
  node,
  readOnly,
  availableValues,
  onChange,
  onDelete,
  onClose,
}: LocalGraphInspectorProps & { node: LocalNode }) {
  const meta = NODE_META[node.type];
  const [confirmDelete, setConfirmDelete] = useState(false);

  function update(patch: Partial<LocalNode>) {
    onChange({ ...node, ...patch });
  }

  function updateConfig(patch: Record<string, unknown>) {
    update({ config: { ...node.config, ...patch } });
  }

  return (
    <aside className="wf-panel wf-inspector" aria-label="Node inspector">
      <header className="wf-panel-head wf-inspector-head">
        <div>
          <h2 title={node.name}>{node.name}</h2>
          <p className="mono" title={node.type}>
            {node.type} · {node.id}
          </p>
        </div>
        <div className="wf-inspector-head-actions">
          <span className={`graph-type-pill graph-type-${meta.tone}`}>{meta.label}</span>
          {onClose ? (
            <button
              type="button"
              className="wf-inspector-close"
              aria-label="Close node inspector"
              onClick={onClose}
            >
              <Icon name="close" size={15} />
            </button>
          ) : null}
        </div>
      </header>

      <div className="wf-inspector-scroll">
        <section className="wf-inspector-section">
          <h3>General</h3>
          <div className="wf-field">
            <label className="field-label" htmlFor={`graph-name-${node.id}`}>
              Display name
            </label>
            <Input
              id={`graph-name-${node.id}`}
              value={node.name}
              maxLength={120}
              disabled={readOnly}
              onChange={(event) => update({ name: event.target.value })}
            />
            <p className="field-hint">Shown on the canvas and in run steps.</p>
          </div>
          <div className="grid-2">
            <div className="wf-field">
              <label className="field-label" htmlFor={`graph-x-${node.id}`}>
                X
              </label>
              <Input
                id={`graph-x-${node.id}`}
                type="number"
                value={Math.round(node.position.x)}
                disabled={readOnly}
                onChange={(event) =>
                  update({ position: { ...node.position, x: Number(event.target.value) } })
                }
              />
            </div>
            <div className="wf-field">
              <label className="field-label" htmlFor={`graph-y-${node.id}`}>
                Y
              </label>
              <Input
                id={`graph-y-${node.id}`}
                type="number"
                value={Math.round(node.position.y)}
                disabled={readOnly}
                onChange={(event) =>
                  update({ position: { ...node.position, y: Number(event.target.value) } })
                }
              />
            </div>
          </div>
        </section>

        <section className="wf-inspector-section">
          <h3>Configuration</h3>
          {node.type === "input" ? (
            <InputNodeEditor
              config={node.config}
              readOnly={readOnly}
              onChange={updateConfig}
            />
          ) : node.type === "llm" ? (
            <LlmNodeEditor
              config={node.config}
              readOnly={readOnly}
              availableValues={availableValues}
              onChange={updateConfig}
            />
          ) : node.type === "agent" ? (
            <AgentNodeEditor
              config={node.config}
              readOnly={readOnly}
              availableValues={availableValues}
              onChange={updateConfig}
            />
          ) : node.type === "tool" ? (
            <ToolNodeEditor config={node.config} readOnly={readOnly} onChange={updateConfig} />
          ) : node.type === "retrieval" ? (
            <RetrievalNodeEditor
              config={node.config}
              readOnly={readOnly}
              availableValues={availableValues}
              onChange={updateConfig}
            />
          ) : node.type === "guardrail" ? (
            <GuardrailNodeEditor config={node.config} readOnly={readOnly} onChange={updateConfig} />
          ) : node.type === "http" ? (
            <HttpNodeEditor config={node.config} readOnly={readOnly} onChange={updateConfig} />
          ) : node.type === "condition" ? (
            <ConditionNodeEditor
              config={node.config}
              readOnly={readOnly}
              onChange={updateConfig}
            />
          ) : (
            <OutputNodeEditor
              config={node.config}
              readOnly={readOnly}
              availableValues={availableValues}
              onChange={updateConfig}
            />
          )}
        </section>
      </div>

      <footer className="wf-inspector-foot">
        <Button
          size="sm"
          variant={confirmDelete ? "danger" : "ghost"}
          disabled={readOnly}
          icon={<Icon name="trash" size={13} />}
          onClick={() => {
            if (confirmDelete) {
              onDelete(node.id);
              return;
            }
            setConfirmDelete(true);
          }}
          onBlur={() => setConfirmDelete(false)}
        >
          {confirmDelete ? "Confirm delete" : "Delete node"}
        </Button>
        <span className="small faint mono">{node.id}</span>
      </footer>
    </aside>
  );
}

interface EditorProps {
  config: Record<string, unknown>;
  readOnly: boolean;
  onChange: (patch: Record<string, unknown>) => void;
}

function InputNodeEditor({ config, readOnly, onChange }: EditorProps) {
  const fields: InputField[] = Array.isArray(config.fields)
    ? (config.fields as InputField[])
    : [];

  function replaceFields(next: InputField[]) {
    onChange({ fields: next });
  }

  function updateField(index: number, patch: Partial<InputField>) {
    replaceFields(fields.map((field, position) => (position === index ? { ...field, ...patch } : field)));
  }

  function addField() {
    const used = new Set(fields.map((field) => field.name));
    let index = fields.length + 1;
    let name = `field_${index}`;
    while (used.has(name)) {
      index += 1;
      name = `field_${index}`;
    }
    replaceFields([
      ...fields,
      { name, type: "string", required: false, default: "", description: "" },
    ]);
  }

  return (
    <div className="stack">
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-input-description">
          Description
        </label>
        <Input
          id="graph-input-description"
          value={typeof config.description === "string" ? config.description : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ description: event.target.value })}
          placeholder="Values supplied by the caller"
        />
      </div>

      <p className="small faint">
        Callers send these fields as the run input. Required fields without a value fail before any
        model call.
      </p>

      {fields.length === 0 ? (
        <p className="small text-danger">An input node should declare at least one field.</p>
      ) : null}

      {fields.map((field, index) => (
        <div className="graph-field-card" key={`${field.name}-${index}`}>
          <div className="wf-two-col">
            <div className="wf-field">
              <label className="field-label" htmlFor={`graph-field-name-${index}`}>
                Field name
              </label>
              <Input
                id={`graph-field-name-${index}`}
                value={field.name}
                disabled={readOnly}
                onChange={(event) => updateField(index, { name: event.target.value })}
              />
            </div>
            <div className="wf-field">
              <label className="field-label" htmlFor={`graph-field-type-${index}`}>
                Type
              </label>
              <Select
                id={`graph-field-type-${index}`}
                value={field.type}
                disabled={readOnly}
                onChange={(event) => {
                  const type = event.target.value as InputFieldType;
                  updateField(index, { type, default: defaultValueForField(type) });
                }}
              >
                {INPUT_FIELD_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </Select>
            </div>
          </div>

          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={Boolean(field.required)}
              disabled={readOnly}
              onChange={(event) => updateField(index, { required: event.target.checked })}
            />
            <span>Required</span>
          </label>

          <div className="wf-field">
            <label className="field-label" htmlFor={`graph-field-desc-${index}`}>
              Description
            </label>
            <Input
              id={`graph-field-desc-${index}`}
              value={field.description ?? ""}
              disabled={readOnly}
              onChange={(event) => updateField(index, { description: event.target.value })}
            />
          </div>

          {field.required ? null : (
            <FieldDefaultEditor
              field={field}
              readOnly={readOnly}
              onChange={(value) => updateField(index, { default: value })}
            />
          )}

          <div className="row">
            <Button
              size="sm"
              variant="ghost"
              disabled={readOnly}
              icon={<Icon name="trash" size={13} />}
              onClick={() => replaceFields(fields.filter((_, position) => position !== index))}
            >
              Remove field
            </Button>
          </div>
        </div>
      ))}

      <Button size="sm" variant="secondary" disabled={readOnly} icon={<Icon name="plus" size={13} />} onClick={addField}>
        Add input field
      </Button>

      {fields.length > 1 ? (
        <p className="small faint">
          Field order is not significant. Use <span className="mono">{"{{ field_name }}"}</span> in
          downstream nodes.
        </p>
      ) : null}
    </div>
  );
}

function FieldDefaultEditor({
  field,
  readOnly,
  onChange,
}: {
  field: InputField;
  readOnly: boolean;
  onChange: (value: unknown) => void;
}) {
  if (field.type === "boolean") {
    return (
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={Boolean(field.default)}
          disabled={readOnly}
          onChange={(event) => onChange(event.target.checked)}
        />
        <span>Default value</span>
      </label>
    );
  }
  if (field.type === "number") {
    return (
      <div className="wf-field">
        <label className="field-label" htmlFor={`graph-field-default-${field.name}`}>
          Default value
        </label>
        <Input
          id={`graph-field-default-${field.name}`}
          type="number"
          value={typeof field.default === "number" ? field.default : 0}
          disabled={readOnly}
          onChange={(event) => onChange(Number(event.target.value))}
        />
      </div>
    );
  }
  if (field.type === "object" || field.type === "array") {
    return (
      <JsonValueField
        id={`graph-field-default-${field.name}`}
        label="Default value (JSON)"
        value={field.default}
        readOnly={readOnly}
        objectOnly={field.type === "object"}
        onChange={onChange}
      />
    );
  }
  return (
    <div className="wf-field">
      <label className="field-label" htmlFor={`graph-field-default-${field.name}`}>
        Default value
      </label>
      <Input
        id={`graph-field-default-${field.name}`}
        value={typeof field.default === "string" ? field.default : ""}
        disabled={readOnly}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function listOf(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function commaList(value: unknown): string {
  return listOf(value).join(", ");
}

function AgentNodeEditor({
  config,
  readOnly,
  availableValues,
  onChange,
}: EditorProps & { availableValues: string[] }) {
  const toolsApi = useApi<ListResponse<Tool>>("/api/v1/tools");
  const skillsApi = useApi<ListResponse<Skill>>("/api/v1/skills");
  const toolIds = listOf(config.tool_ids);
  const skillIds = listOf(config.skill_ids);
  const temperature = typeof config.temperature === "number" ? config.temperature : "";
  const maxTokens = typeof config.max_tokens === "number" ? config.max_tokens : "";

  function toggle(key: "tool_ids" | "skill_ids", id: string) {
    const current = listOf(config[key]);
    onChange({
      [key]: current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    });
  }

  return (
    <div className="stack">
      <div className="wf-callout">
        <span className="wf-callout-icon"><Icon name="bot" size={15} /></span>
        <div>
          <strong>What an agent node does</strong>
          <p>
            It gives the model the selected tools and skills, lets it call tools in a bounded loop,
            and returns the final answer. Use it when the work needs decisions, not just one prompt.
          </p>
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-agent-prompt">
          Task prompt <span className="field-required">*</span>
        </label>
        <Textarea
          id="graph-agent-prompt"
          className="textarea-mono"
          rows={6}
          value={typeof config.prompt === "string" ? config.prompt : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ prompt: event.target.value })}
        />
        <ValueTokens values={availableValues} />
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-agent-system">
          System instruction
        </label>
        <Textarea
          id="graph-agent-system"
          rows={5}
          value={typeof config.system === "string" ? config.system : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ system: event.target.value })}
        />
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-agent-model">
          Model override
        </label>
        <Input
          id="graph-agent-model"
          value={typeof config.model === "string" ? config.model : ""}
          disabled={readOnly}
          placeholder="Agent setting or connection default"
          onChange={(event) => onChange({ model: event.target.value || null })}
        />
        <p className="small faint">
          Leave empty to use the agent settings model. Example: openrouter/auto.
        </p>
      </div>
      <div className="wf-two-col">
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-agent-temperature">Temperature</label>
          <Input
            id="graph-agent-temperature"
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            disabled={readOnly}
            onChange={(event) =>
              onChange({ temperature: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </div>
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-agent-max-tokens">Max tokens</label>
          <Input
            id="graph-agent-max-tokens"
            type="number"
            min={1}
            value={maxTokens}
            disabled={readOnly}
            onChange={(event) =>
              onChange({ max_tokens: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-agent-steps">Maximum tool steps</label>
        <Input
          id="graph-agent-steps"
          type="number"
          min={1}
          max={12}
          value={typeof config.max_steps === "number" ? config.max_steps : 6}
          disabled={readOnly}
          onChange={(event) => onChange({ max_steps: Number(event.target.value) })}
        />
        <p className="field-hint">A hard stop. The loop cannot run longer than this, so cost stays bounded.</p>
      </div>
      <ContextEditor config={config} readOnly={readOnly} onChange={onChange} />

      <div className="wf-field">
        <span className="field-label">Tools</span>
        {toolsApi.data?.items.length ? (
          <div className="graph-check-list">
            {toolsApi.data.items.map((tool) => (
              <label className="checkbox-row" key={tool.id}>
                <input
                  type="checkbox"
                  checked={toolIds.includes(tool.id)}
                  disabled={readOnly || !tool.enabled}
                  onChange={() => toggle("tool_ids", tool.id)}
                />
                <span>
                  <strong>{tool.name}</strong>{" "}
                  <span className="small faint">
                    {tool.kind.toUpperCase()} · {tool.description || "no description"}
                  </span>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="small faint">
            No tools registered yet. Create one in <span className="mono">Tools &amp; MCP</span>, then come back.
          </p>
        )}
      </div>
      <div className="wf-field">
        <span className="field-label">Skills</span>
        {skillsApi.data?.items.length ? (
          <div className="graph-check-list">
            {skillsApi.data.items.map((skill) => (
              <label className="checkbox-row" key={skill.id}>
                <input
                  type="checkbox"
                  checked={skillIds.includes(skill.id)}
                  disabled={readOnly}
                  onChange={() => toggle("skill_ids", skill.id)}
                />
                <span>
                  <strong>{skill.name}</strong> <span className="small faint">{skill.description}</span>
                </span>
              </label>
            ))}
          </div>
        ) : (
          <p className="small faint">
            No skills yet. Create one in <span className="mono">Skills</span> to share rules across agents.
          </p>
        )}
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-agent-output">Output key</label>
        <Input
          id="graph-agent-output"
          value={typeof config.output_key === "string" ? config.output_key : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ output_key: event.target.value })}
        />
      </div>
    </div>
  );
}

function ToolNodeEditor({ config, readOnly, onChange }: EditorProps) {
  const toolsApi = useApi<ListResponse<Tool>>("/api/v1/tools");
  return (
    <div className="stack">
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-tool-id">Registered tool</label>
        <Select
          id="graph-tool-id"
          value={typeof config.tool_id === "string" ? config.tool_id : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ tool_id: event.target.value })}
        >
          <option value="">Select a tool…</option>
          {(toolsApi.data?.items ?? []).map((tool) => (
            <option key={tool.id} value={tool.id}>
              {tool.name} ({tool.kind})
            </option>
          ))}
        </Select>
      </div>
      <JsonValueField
        id="graph-tool-arguments"
        label="Arguments (JSON)"
        value={config.arguments}
        readOnly={readOnly}
        objectOnly
        onChange={(value) => onChange({ arguments: value })}
        hint='Values support placeholders, for example {"query": "{{ message }}"}.'
      />
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-tool-output">Output key</label>
        <Input
          id="graph-tool-output"
          value={typeof config.output_key === "string" ? config.output_key : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ output_key: event.target.value })}
        />
      </div>
    </div>
  );
}

function GuardrailNodeEditor({ config, readOnly, onChange }: EditorProps) {
  return (
    <div className="stack">
      <div className="wf-callout">
        <span className="wf-callout-icon"><Icon name="shield" size={15} /></span>
        <div>
          <strong>Two branches, no guessing</strong>
          <p>
            The pass branch continues. The fail branch must also end at an output, so a rejected
            answer is visible instead of silently forwarded.
          </p>
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-preset">Preset</label>
        <Select
          id="graph-guardrail-preset"
          value={typeof config.preset === "string" ? config.preset : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ preset: event.target.value })}
        >
          <option value="">Custom rules only</option>
          <option value="pii">Block personal data (email, phone, card)</option>
          <option value="prompt_injection">Block prompt-injection phrases</option>
          <option value="json_object">Require a valid JSON object</option>
          <option value="safe_text">Safe text (custom terms only)</option>
        </Select>
        <p className="field-hint">
          Presets run before the term and pattern rules below. Every failure reason is shown
          in the run timeline.
        </p>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-path">Value path <span className="field-required">*</span></label>
        <Input
          id="graph-guardrail-path"
          value={typeof config.path === "string" ? config.path : ""}
          disabled={readOnly}
          placeholder="decision"
          onChange={(event) => onChange({ path: event.target.value })}
        />
      </div>
      <div className="wf-two-col">
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-guardrail-min">Minimum characters</label>
          <Input
            id="graph-guardrail-min"
            type="number"
            min={0}
            value={typeof config.min_chars === "number" ? config.min_chars : ""}
            disabled={readOnly}
            onChange={(event) =>
              onChange({ min_chars: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </div>
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-guardrail-max">Maximum characters</label>
          <Input
            id="graph-guardrail-max"
            type="number"
            min={1}
            value={typeof config.max_chars === "number" ? config.max_chars : ""}
            disabled={readOnly}
            onChange={(event) =>
              onChange({ max_chars: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-deny">Blocked terms</label>
        <Input
          id="graph-guardrail-deny"
          value={commaList(config.deny_terms)}
          disabled={readOnly}
          placeholder="password, secret, internal-only"
          onChange={(event) =>
            onChange({
              deny_terms: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-require">Required terms</label>
        <Input
          id="graph-guardrail-require"
          value={commaList(config.require_terms)}
          disabled={readOnly}
          placeholder="recommended_technician_id, summary"
          onChange={(event) =>
            onChange({
              require_terms: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
            })
          }
        />
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-pattern">Pattern (regex)</label>
        <Input
          id="graph-guardrail-pattern"
          value={typeof config.pattern === "string" ? config.pattern : ""}
          disabled={readOnly}
          placeholder="Optional"
          onChange={(event) => onChange({ pattern: event.target.value })}
        />
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-guardrail-mode">Pattern rule</label>
        <Select
          id="graph-guardrail-mode"
          value={typeof config.pattern_mode === "string" ? config.pattern_mode : "deny"}
          disabled={readOnly}
          onChange={(event) => onChange({ pattern_mode: event.target.value })}
        >
          <option value="deny">Fail if the pattern matches</option>
          <option value="allow">Fail if the pattern does not match</option>
        </Select>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={Boolean(config.case_sensitive)}
          disabled={readOnly}
          onChange={(event) => onChange({ case_sensitive: event.target.checked })}
        />
        <span>Case-sensitive matching</span>
      </label>
    </div>
  );
}

function ContextEditor({
  config,
  readOnly,
  onChange,
}: EditorProps) {
  const context = (config.context && typeof config.context === "object"
    ? config.context
    : {}) as Record<string, unknown>;
  function update(patch: Record<string, unknown>) {
    onChange({ context: { ...context, ...patch } });
  }
  const history = Boolean(context.history);
  return (
    <div className="wf-field">
      <span className="field-label">Context &amp; memory</span>
      <div className="wf-callout wf-callout-compact">
        <span className="wf-callout-icon"><Icon name="layers" size={14} /></span>
        <p>
          History lets a chat agent remember earlier turns. The character budget trims the
          oldest history first, never the current prompt.
        </p>
      </div>
      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={history}
          disabled={readOnly}
          onChange={(event) => update({ history: event.target.checked })}
        />
        <span>Include conversation history</span>
      </label>
      {history ? (
        <div className="wf-two-col">
          <div className="wf-field">
            <label className="field-label" htmlFor={`history-path-${String(config.output_key ?? "node")}`}>
              History value path
            </label>
            <Input
              id={`history-path-${String(config.output_key ?? "node")}`}
              value={String(context.history_path ?? "history")}
              disabled={readOnly}
              placeholder="history"
              onChange={(event) => update({ history_path: event.target.value })}
            />
            <p className="field-hint">A list of {"{role, content}"} objects in the input.</p>
          </div>
          <div className="wf-field">
            <label className="field-label" htmlFor={`history-turns-${String(config.output_key ?? "node")}`}>
              Last messages
            </label>
            <Input
              id={`history-turns-${String(config.output_key ?? "node")}`}
              type="number"
              min={0}
              max={50}
              value={Number(context.max_history_messages ?? 6)}
              disabled={readOnly}
              onChange={(event) => update({ max_history_messages: Number(event.target.value) })}
            />
          </div>
        </div>
      ) : null}
      <div className="wf-field">
        <label className="field-label" htmlFor={`context-budget-${String(config.output_key ?? "node")}`}>
          Context character budget
        </label>
        <Input
          id={`context-budget-${String(config.output_key ?? "node")}`}
          type="number"
          min={500}
          max={50000}
          step={500}
          value={Number(context.max_context_chars ?? 8000)}
          disabled={readOnly}
          onChange={(event) => update({ max_context_chars: Number(event.target.value) })}
        />
        <p className="field-hint">System + history + prompt are trimmed to this size.</p>
      </div>
    </div>
  );
}

function RetrievalNodeEditor({
  config,
  readOnly,
  availableValues,
  onChange,
}: EditorProps & { availableValues: string[] }) {
  const bases = useApi<ListResponse<KnowledgeBase>>("/api/v1/knowledge-bases");
  const topK = typeof config.top_k === "number" ? config.top_k : 5;
  const minScore = typeof config.min_score === "number" ? config.min_score : "";
  return (
    <div className="stack">
      <div className="wf-callout">
        <span className="wf-callout-icon"><Icon name="database" size={15} /></span>
        <div>
          <strong>Ground the answer in your documents</strong>
          <p>
            The node embeds the question, ranks the knowledge base chunks and writes the
            best ones to an output key. Pass that key to an LLM prompt as context.
          </p>
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-retrieval-base">
          Knowledge base <span className="field-required">*</span>
        </label>
        <Select
          id="graph-retrieval-base"
          value={typeof config.knowledge_base_id === "string" ? config.knowledge_base_id : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ knowledge_base_id: event.target.value })}
        >
          <option value="">Select a knowledge base…</option>
          {(bases.data?.items ?? []).map((base) => (
            <option key={base.id} value={base.id}>
              {base.name} ({base.mode}, {base.document_count} docs)
            </option>
          ))}
        </Select>
        {bases.data?.items.length === 0 ? (
          <p className="field-hint">
            No knowledge bases yet. Create one in <span className="mono">Knowledge</span>, then
            return here.
          </p>
        ) : null}
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-retrieval-query">
          Query template <span className="field-required">*</span>
        </label>
        <Input
          id="graph-retrieval-query"
          value={typeof config.query === "string" ? config.query : ""}
          disabled={readOnly}
          placeholder="{{ question }}"
          onChange={(event) => onChange({ query: event.target.value })}
        />
        <p className="field-hint">Usually the user question from the input node.</p>
        <ValueTokens values={availableValues} />
      </div>
      <div className="wf-two-col">
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-retrieval-topk">
            Chunks to return
          </label>
          <Input
            id="graph-retrieval-topk"
            type="number"
            min={1}
            max={20}
            value={topK}
            disabled={readOnly}
            onChange={(event) => onChange({ top_k: Number(event.target.value) })}
          />
        </div>
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-retrieval-min">
            Minimum relevance
          </label>
          <Input
            id="graph-retrieval-min"
            type="number"
            min={0}
            max={1}
            step={0.05}
            value={minScore}
            disabled={readOnly}
            placeholder="No minimum"
            onChange={(event) =>
              onChange({ min_score: event.target.value === "" ? null : Number(event.target.value) })
            }
          />
        </div>
      </div>
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-retrieval-output">
          Output key
        </label>
        <Input
          id="graph-retrieval-output"
          value={typeof config.output_key === "string" ? config.output_key : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ output_key: event.target.value })}
        />
        <p className="field-hint">
          The context string. A <span className="mono">_results</span> key also carries the
          scored chunks.
        </p>
      </div>
    </div>
  );
}

function LlmNodeEditor({
  config,
  readOnly,
  availableValues,
  onChange,
}: EditorProps & { availableValues: string[] }) {
  const temperature = typeof config.temperature === "number" ? config.temperature : "";
  const maxTokens = typeof config.max_tokens === "number" ? config.max_tokens : "";

  return (
    <div className="stack">
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-llm-prompt">
          Prompt <span className="field-required">*</span>
        </label>
        <Textarea
          id="graph-llm-prompt"
          className="textarea-mono"
          rows={6}
          value={typeof config.prompt === "string" ? config.prompt : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ prompt: event.target.value })}
        />
        <p className="field-hint">
          Supports <span className="mono">{"{{ value }}"}</span> placeholders.
          {availableValues.length > 0 ? " Available values:" : ""}
        </p>
        <ValueTokens values={availableValues} />
      </div>

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-llm-system">
          System instruction
        </label>
        <Textarea
          id="graph-llm-system"
          rows={4}
          value={typeof config.system === "string" ? config.system : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ system: event.target.value })}
        />
      </div>

      <ContextEditor config={config} readOnly={readOnly} onChange={onChange} />

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-llm-model">
          Model override
        </label>
        <Input
          id="graph-llm-model"
          value={typeof config.model === "string" ? config.model : ""}
          disabled={readOnly}
          placeholder="Use the connection default"
          onChange={(event) => onChange({ model: event.target.value.trim() || null })}
        />
        <p className="field-hint">Leave empty to use the connection&apos;s default model.</p>
      </div>

      <div className="wf-two-col">
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-llm-temperature">
            Temperature
          </label>
          <Input
            id="graph-llm-temperature"
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={temperature}
            disabled={readOnly}
            placeholder="Model default"
            onChange={(event) =>
              onChange({
                temperature: event.target.value === "" ? null : Number(event.target.value),
              })
            }
          />
        </div>
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-llm-max-tokens">
            Max tokens
          </label>
          <Input
            id="graph-llm-max-tokens"
            type="number"
            min={1}
            value={maxTokens}
            disabled={readOnly}
            placeholder="Model default"
            onChange={(event) =>
              onChange({
                max_tokens: event.target.value === "" ? null : Number(event.target.value),
              })
            }
          />
        </div>
      </div>

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-llm-output-key">
          Output key
        </label>
        <Input
          id="graph-llm-output-key"
          value={typeof config.output_key === "string" ? config.output_key : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ output_key: event.target.value })}
        />
        <p className="field-hint">Downstream nodes read the answer from this key.</p>
      </div>
    </div>
  );
}

function HttpNodeEditor({ config, readOnly, onChange }: EditorProps) {
  const method = typeof config.method === "string" ? config.method : "GET";
  const methodDisallowsBody = method === "GET" || method === "DELETE";

  return (
    <div className="stack">
      <div className="grid-2">
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-http-method">
            Method
          </label>
          <Select
            id="graph-http-method"
            value={method}
            disabled={readOnly}
            onChange={(event) => onChange({ method: event.target.value })}
          >
            {HTTP_METHODS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </Select>
        </div>
        <div className="wf-field">
          <label className="field-label" htmlFor="graph-http-timeout">
            Timeout (seconds)
          </label>
          <Input
            id="graph-http-timeout"
            type="number"
            min={1}
            max={120}
            value={typeof config.timeout_seconds === "number" ? config.timeout_seconds : 30}
            disabled={readOnly}
            onChange={(event) => onChange({ timeout_seconds: Number(event.target.value) })}
          />
        </div>
      </div>

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-http-url">
          URL <span className="field-required">*</span>
        </label>
        <Input
          id="graph-http-url"
          value={typeof config.url === "string" ? config.url : ""}
          disabled={readOnly}
          placeholder="https://api.example.com/items/{{ item_id }}"
          onChange={(event) => onChange({ url: event.target.value })}
        />
        <p className="field-hint">
          Placeholders are rendered before the request. Non-2xx responses fail the run.
        </p>
      </div>

      <JsonValueField
        id="graph-http-headers"
        label="Headers (JSON object)"
        value={config.headers}
        readOnly={readOnly}
        objectOnly
        onChange={(value) => onChange({ headers: value })}
      />

      <JsonValueField
        id="graph-http-body"
        label="Body (JSON)"
        value={config.body}
        readOnly={readOnly || methodDisallowsBody}
        onChange={(value) => onChange({ body: value })}
        hint={
          methodDisallowsBody
            ? `${method} requests cannot send a body.`
            : "JSON body with optional placeholders. Whole-value placeholders keep their type."
        }
      />

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-http-output-key">
          Output key
        </label>
        <Input
          id="graph-http-output-key"
          value={typeof config.output_key === "string" ? config.output_key : ""}
          disabled={readOnly}
          onChange={(event) => onChange({ output_key: event.target.value })}
        />
      </div>

      <div className="wf-callout">
        <span className="wf-callout-icon">
          <Icon name="alert" size={15} />
        </span>
        <div>
          <strong>Outbound network access</strong>
          <p>
            HTTP nodes call whatever URL the graph contains. Only operators you trust should be able
            to edit graphs.
          </p>
        </div>
      </div>
    </div>
  );
}

function ConditionNodeEditor({ config, readOnly, onChange }: EditorProps) {
  const operator = typeof config.operator === "string" ? config.operator : "truthy";
  const needsValue = VALUE_OPERATORS.has(operator as ConditionOperator);

  return (
    <div className="stack">
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-condition-path">
          Value path <span className="field-required">*</span>
        </label>
        <Input
          id="graph-condition-path"
          value={typeof config.path === "string" ? config.path : ""}
          disabled={readOnly}
          placeholder="message"
          onChange={(event) => onChange({ path: event.target.value })}
        />
        <p className="field-hint">
          Dot/bracket path into the run values, for example <span className="mono">order.total</span>{" "}
          or <span className="mono">items[0].status</span>.
        </p>
      </div>

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-condition-operator">
          Operator
        </label>
        <Select
          id="graph-condition-operator"
          value={operator}
          disabled={readOnly}
          onChange={(event) => {
            const next = event.target.value;
            onChange({
              operator: next,
              value:
                VALUE_OPERATORS.has(next as ConditionOperator) && (config.value === null || config.value === undefined)
                  ? ""
                  : config.value,
            });
          }}
        >
          {CONDITION_OPERATORS.map((item) => (
            <option key={item} value={item}>
              {item.replace(/_/g, " ")}
            </option>
          ))}
        </Select>
      </div>

      {needsValue ? (
        <JsonValueField
          id="graph-condition-value"
          label="Comparison value (JSON)"
          value={config.value}
          readOnly={readOnly}
          onChange={(value) => onChange({ value })}
          hint='Use JSON so types survive, for example "hello", 5, true, or ["a", "b"].'
        />
      ) : null}

      <p className="small faint">
        The <span className="mono">true</span> branch runs when the comparison is true. Both branches
        must terminate in output nodes.
      </p>
    </div>
  );
}

function OutputNodeEditor({
  config,
  readOnly,
  availableValues,
  onChange,
}: EditorProps & { availableValues: string[] }) {
  return (
    <div className="stack">
      <div className="wf-field">
        <label className="field-label" htmlFor="graph-output-path">
          Value path
        </label>
        <Input
          id="graph-output-path"
          value={typeof config.path === "string" ? config.path : ""}
          disabled={readOnly}
          placeholder="answer"
          onChange={(event) => onChange({ path: event.target.value })}
        />
        <p className="field-hint">Used when no template is set.</p>
      </div>

      <div className="wf-field">
        <label className="field-label" htmlFor="graph-output-template">
          Template
        </label>
        <Textarea
          id="graph-output-template"
          className="textarea-mono"
          rows={4}
          value={typeof config.template === "string" ? config.template : ""}
          disabled={readOnly}
          placeholder="Answer: {{ answer }}"
          onChange={(event) => onChange({ template: event.target.value })}
        />
        <p className="field-hint">Takes precedence over the value path when non-empty.</p>
        <ValueTokens values={availableValues} />
      </div>
    </div>
  );
}

function ValueTokens({ values }: { values: string[] }) {
  if (values.length === 0) return null;
  return (
    <div className="graph-token-list">
      {values.map((value) => (
        <span className="graph-token" key={value}>
          {`{{ ${value} }}`}
        </span>
      ))}
    </div>
  );
}

function JsonValueField({
  id,
  label,
  value,
  readOnly,
  objectOnly = false,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  value: unknown;
  readOnly: boolean;
  objectOnly?: boolean;
  onChange: (value: unknown) => void;
  hint?: string;
}) {
  const [text, setText] = useState(() => jsonText(value));
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setText(jsonText(value));
    setError(null);
  }, [value]);

  function commit() {
    if (readOnly) return;
    let parsed: unknown;
    try {
      parsed = JSON.parse(text);
    } catch {
      setError("Enter valid JSON.");
      return;
    }
    if (objectOnly && (parsed === null || typeof parsed !== "object" || Array.isArray(parsed))) {
      setError("This field requires a JSON object.");
      return;
    }
    setError(null);
    onChange(parsed);
  }

  return (
    <Field label={label} htmlFor={id} hint={hint ?? "Edited as JSON. Changes apply when the field loses focus."} error={error}>
      <Textarea
        id={id}
        className="textarea-mono"
        rows={4}
        spellCheck={false}
        value={text}
        disabled={readOnly}
        onChange={(event) => setText(event.target.value)}
        onBlur={commit}
      />
    </Field>
  );
}

function jsonText(value: unknown): string {
  if (value === undefined) return "";
  if (value === null) return "null";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
