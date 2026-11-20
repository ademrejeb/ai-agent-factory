"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useToast } from "@/components/providers/ToastProvider";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import type { ListResponse, Skill } from "@/lib/types";

export default function SkillsPage() {
  const toast = useToast();
  const skills = useApi<ListResponse<Skill>>("/api/v1/skills");
  const [editing, setEditing] = useState<Skill | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [instructions, setInstructions] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function reset() {
    setEditing(null);
    setName("");
    setDescription("");
    setInstructions("");
    setError(null);
  }

  function edit(skill: Skill) {
    setEditing(skill);
    setName(skill.name);
    setDescription(skill.description);
    setInstructions(skill.instructions);
    setError(null);
  }

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = { name, description, instructions };
      if (editing) {
        await api.patch(`/api/v1/skills/${editing.id}`, body);
        toast.push("Skill updated. Agent nodes using it pick up the new instructions.", "success");
      } else {
        await api.post("/api/v1/skills", body);
        toast.push("Skill created. Attach it to an agent or an agent node.", "success");
      }
      reset();
      skills.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function remove(skill: Skill) {
    if (!window.confirm(`Delete skill "${skill.name}"?`)) return;
    try {
      await api.del(`/api/v1/skills/${skill.id}`);
      toast.push("Skill deleted.", "success");
      skills.reload();
    } catch (err) {
      toast.push(errorMessage(err), "error");
    }
  }

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Capabilities"
        title="Skills"
        description="Reusable instruction blocks. They are appended to the system prompt of every agent node that uses them, so a rule lives in one place instead of being copied into six graphs."
        actions={
          <Button variant="secondary" icon={<Icon name="refresh" size={15} />} onClick={skills.reload}>
            Refresh
          </Button>
        }
      />

      <div className="grid-main">
        <Card title="Skill library" padded={false}>
          {skills.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={skills.error} onRetry={skills.reload} />
            </div>
          ) : skills.loading && !skills.data ? (
            <LoadingBlock rows={5} />
          ) : (skills.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              icon="shield"
              title="No skills yet"
              description="Write the rules once here, then attach them to agents. Good first skills: never invent ids, always return the requested JSON shape, escalate when confidence is low."
            />
          ) : (
            <ul className="list-plain">
              {skills.data?.items.map((skill) => (
                <li className="list-item" key={skill.id}>
                  <div>
                    <p className="list-item-title">{skill.name}</p>
                    <p className="list-item-meta">{skill.description || "No description."}</p>
                    <p className="list-item-meta skill-preview">{skill.instructions}</p>
                  </div>
                  <div className="stack-sm" style={{ alignItems: "flex-end" }}>
                    <Button size="sm" variant="secondary" onClick={() => edit(skill)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void remove(skill)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title={editing ? `Edit ${editing.name}` : "Add a skill"}>
          <form className="stack" onSubmit={save}>
            {error ? <InlineError message={error} /> : null}
            <Field label="Name" htmlFor="skill-name" required>
              <Input
                id="skill-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Dispatch safety rules"
                required
              />
            </Field>
            <Field label="What it is for" htmlFor="skill-description">
              <Input
                id="skill-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Shown to operators in the library."
              />
            </Field>
            <Field
              label="Instructions"
              htmlFor="skill-instructions"
              hint="Written as an instruction to the model. Be specific about refusals and output shape."
              required
            >
              <Textarea
                id="skill-instructions"
                className="textarea-mono"
                rows={12}
                value={instructions}
                onChange={(event) => setInstructions(event.target.value)}
                required
              />
            </Field>
            <div className="row">
              <Button type="submit" loading={busy}>
                {editing ? "Save changes" : "Create skill"}
              </Button>
              {editing ? (
                <Button type="button" variant="ghost" onClick={reset}>
                  Cancel
                </Button>
              ) : null}
            </div>
          </form>
        </Card>
      </div>
    </div>
  );
}
