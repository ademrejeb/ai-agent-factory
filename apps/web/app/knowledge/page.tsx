"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Field, Input, Select, Textarea } from "@/components/ui/Field";
import { Icon } from "@/components/ui/Icon";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorBlock, InlineError, LoadingBlock } from "@/components/ui/States";
import { useToast } from "@/components/providers/ToastProvider";
import { useApi } from "@/hooks/useApi";
import { api, errorMessage } from "@/lib/api";
import type {
  KnowledgeBase,
  KnowledgeSearchResponse,
  ListResponse,
  ProviderConnection,
} from "@/lib/types";

const TEXT_EXTENSIONS = [".txt", ".md", ".markdown", ".csv", ".json", ".log", ".yaml", ".yml"];
const MAX_FILE_BYTES = 2_000_000;

export default function KnowledgePage() {
  const toast = useToast();
  const bases = useApi<ListResponse<KnowledgeBase>>("/api/v1/knowledge-bases");
  const connections = useApi<ListResponse<ProviderConnection>>("/api/v1/provider-connections");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = useApi<KnowledgeBase>(
    selectedId ? `/api/v1/knowledge-bases/${selectedId}` : null,
  );

  const [editing, setEditing] = useState<KnowledgeBase | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<"lexical" | "vector">("lexical");
  const [connectionId, setConnectionId] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [chunkSize, setChunkSize] = useState("1200");
  const [chunkOverlap, setChunkOverlap] = useState("200");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [docName, setDocName] = useState("");
  const [docText, setDocText] = useState("");
  const [docBusy, setDocBusy] = useState(false);
  const [docError, setDocError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const [query, setQuery] = useState("");
  const [searchBusy, setSearchBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [search, setSearch] = useState<KnowledgeSearchResponse | null>(null);

  const baseItems = bases.data?.items ?? [];
  const langchainConnections = useMemo(
    () => (connections.data?.items ?? []).filter((item) => item.provider === "langchain"),
    [connections.data],
  );

  useEffect(() => {
    if (!selectedId && baseItems.length > 0) setSelectedId(baseItems[0].id);
  }, [baseItems, selectedId]);

  useEffect(() => {
    setSearch(null);
    setSearchError(null);
  }, [selectedId]);

  function resetForm() {
    setEditing(null);
    setName("");
    setDescription("");
    setMode("lexical");
    setConnectionId("");
    setEmbeddingModel("");
    setChunkSize("1200");
    setChunkOverlap("200");
    setError(null);
  }

  function startEdit(base: KnowledgeBase) {
    setEditing(base);
    setName(base.name);
    setDescription(base.description);
    setMode(base.mode === "vector" ? "vector" : "lexical");
    setConnectionId(base.embedding_connection_id ?? "");
    setEmbeddingModel(base.embedding_model ?? "");
    setChunkSize(String(base.chunk_size));
    setChunkOverlap(String(base.chunk_overlap));
    setError(null);
  }

  async function saveBase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        name: name.trim(),
        description,
        mode,
        embedding_connection_id: mode === "vector" ? connectionId || null : null,
        embedding_model: mode === "vector" ? embeddingModel.trim() || null : null,
        chunk_size: Number(chunkSize) || 1200,
        chunk_overlap: Number(chunkOverlap) || 0,
      };
      if (editing) {
        const updated = await api.patch<KnowledgeBase>(
          `/api/v1/knowledge-bases/${editing.id}`,
          body,
        );
        toast.push("Knowledge base updated.", "success");
        setSelectedId(updated.id);
      } else {
        const created = await api.post<KnowledgeBase>("/api/v1/knowledge-bases", body);
        toast.push("Knowledge base created. Add a document next.", "success");
        setSelectedId(created.id);
      }
      resetForm();
      bases.reload();
      selected.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function removeBase(base: KnowledgeBase) {
    if (!window.confirm(`Delete "${base.name}" and all of its documents?`)) return;
    try {
      await api.del(`/api/v1/knowledge-bases/${base.id}`);
      toast.push("Knowledge base deleted.", "success");
      if (selectedId === base.id) setSelectedId(null);
      bases.reload();
    } catch (err) {
      toast.push(errorMessage(err), "error");
    }
  }

  function readFile(file: File) {
    setDocError(null);
    const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
    if (!TEXT_EXTENSIONS.includes(extension)) {
      setDocError("Supported files: plain text, Markdown, CSV, JSON, YAML or LOG.");
      return;
    }
    if (file.size > MAX_FILE_BYTES) {
      setDocError("This file is larger than 2 MB. Split it into smaller documents.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      setDocName(file.name);
      setDocText(String(reader.result ?? ""));
    };
    reader.onerror = () => setDocError("Could not read this file.");
    reader.readAsText(file);
  }

  async function addDocument(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId) return;
    setDocBusy(true);
    setDocError(null);
    try {
      await api.post(`/api/v1/knowledge-bases/${selectedId}/documents`, {
        name: docName.trim() || "Pasted text",
        text: docText,
        mime_type: "text/plain",
      });
      toast.push("Document indexed. It is now searchable.", "success");
      setDocName("");
      setDocText("");
      if (fileRef.current) fileRef.current.value = "";
      selected.reload();
      bases.reload();
    } catch (err) {
      setDocError(errorMessage(err));
    } finally {
      setDocBusy(false);
    }
  }

  async function removeDocument(documentId: string, documentName: string) {
    if (!selectedId) return;
    if (!window.confirm(`Remove "${documentName}" from this knowledge base?`)) return;
    try {
      await api.del(`/api/v1/knowledge-bases/${selectedId}/documents/${documentId}`);
      toast.push("Document removed.", "success");
      selected.reload();
      bases.reload();
    } catch (err) {
      toast.push(errorMessage(err), "error");
    }
  }

  async function runSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedId || !query.trim()) return;
    setSearchBusy(true);
    setSearchError(null);
    try {
      const result = await api.post<KnowledgeSearchResponse>(
        `/api/v1/knowledge-bases/${selectedId}/search`,
        { query: query.trim(), top_k: 5 },
      );
      setSearch(result);
    } catch (err) {
      setSearchError(errorMessage(err));
    } finally {
      setSearchBusy(false);
    }
  }

  const active = selected.data;

  return (
    <div className="stack-lg">
      <PageHeader
        eyebrow="Context"
        title="Knowledge"
        description="Give agents a source of truth. Add policies, FAQs or product notes, then use a Retrieval node in the graph to ground the answer. Retrieval returns the best chunks with a relevance score, so you can see exactly what the model saw."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<Icon name="refresh" size={15} />}
              onClick={() => {
                bases.reload();
                selected.reload();
              }}
            >
              Refresh
            </Button>
            <Button
              variant="primary"
              icon={<Icon name="plus" size={15} />}
              onClick={() => {
                resetForm();
                document.getElementById("knowledge-form")?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              New knowledge base
            </Button>
          </>
        }
      />

      <div className="knowledge-layout">
        <Card title="Your knowledge bases" padded={false}>
          {bases.error ? (
            <div style={{ padding: 16 }}>
              <ErrorBlock message={bases.error} onRetry={bases.reload} />
            </div>
          ) : bases.loading && !bases.data ? (
            <LoadingBlock rows={4} />
          ) : baseItems.length === 0 ? (
            <EmptyState
              icon="database"
              title="No knowledge bases yet"
              description="Create one on the right. Start with the support FAQ or the policy handbook your agents keep asking about."
            />
          ) : (
            <ul className="list-plain">
              {baseItems.map((base) => (
                <li
                  key={base.id}
                  className={`knowledge-item ${selectedId === base.id ? "knowledge-item-active" : ""}`}
                >
                  <button type="button" className="knowledge-item-main" onClick={() => setSelectedId(base.id)}>
                    <div className="knowledge-item-title">
                      <strong>{base.name}</strong>
                      <Badge tone={base.mode === "vector" ? "info" : "neutral"}>
                        {base.mode === "vector" ? "embeddings" : "keyword"}
                      </Badge>
                    </div>
                    <p className="list-item-meta">
                      {base.document_count} document{base.document_count === 1 ? "" : "s"} ·{" "}
                      {base.chunk_count} chunk{base.chunk_count === 1 ? "" : "s"}
                    </p>
                    {base.description ? <p className="list-item-meta">{base.description}</p> : null}
                  </button>
                  <div className="knowledge-item-actions">
                    <Button size="sm" variant="ghost" onClick={() => startEdit(base)}>
                      Edit
                    </Button>
                    <Button size="sm" variant="ghost" onClick={() => void removeBase(base)}>
                      Delete
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card
          title={editing ? `Edit ${editing.name}` : "Create a knowledge base"}
          description="Keyword mode needs no extra service. Embeddings mode calls the connection's /embeddings endpoint for better semantic matches."
        >
          <form id="knowledge-form" className="stack" onSubmit={saveBase}>
            {error ? <InlineError message={error} /> : null}
            <Field label="Name" htmlFor="kb-name" required>
              <Input
                id="kb-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Support policy 2026"
                required
              />
            </Field>
            <Field label="What is inside" htmlFor="kb-description">
              <Input
                id="kb-description"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                placeholder="Refund rules, SLAs and escalation contacts."
              />
            </Field>
            <div className="form-grid">
              <Field
                label="Search mode"
                htmlFor="kb-mode"
                hint="Keyword works everywhere. Embeddings need an OpenAI-compatible /embeddings endpoint."
              >
                <Select
                  id="kb-mode"
                  value={mode}
                  onChange={(event) => setMode(event.target.value as "lexical" | "vector")}
                >
                  <option value="lexical">Keyword (no extra service)</option>
                  <option value="vector">Embeddings (semantic)</option>
                </Select>
              </Field>
              <Field label="Chunk size" htmlFor="kb-chunk" hint="Characters per chunk.">
                <Input
                  id="kb-chunk"
                  type="number"
                  min={200}
                  max={8000}
                  value={chunkSize}
                  onChange={(event) => setChunkSize(event.target.value)}
                />
              </Field>
            </div>
            <div className="form-grid">
              <Field label="Chunk overlap" htmlFor="kb-overlap" hint="Shared characters between chunks.">
                <Input
                  id="kb-overlap"
                  type="number"
                  min={0}
                  max={2000}
                  value={chunkOverlap}
                  onChange={(event) => setChunkOverlap(event.target.value)}
                />
              </Field>
              {mode === "vector" ? (
                <Field
                  label="Embedding connection"
                  htmlFor="kb-connection"
                  hint="The model endpoint that exposes /embeddings."
                  required
                >
                  <Select
                    id="kb-connection"
                    value={connectionId}
                    onChange={(event) => setConnectionId(event.target.value)}
                    required
                  >
                    <option value="">Select a connection…</option>
                    {langchainConnections.map((connection) => (
                      <option key={connection.id} value={connection.id}>
                        {connection.name}
                      </option>
                    ))}
                  </Select>
                </Field>
              ) : null}
            </div>
            {mode === "vector" ? (
              <Field
                label="Embedding model"
                htmlFor="kb-embedding-model"
                hint="For Ollama this is usually nomic-embed-text; for OpenAI text-embedding-3-small."
                required
              >
                <Input
                  id="kb-embedding-model"
                  value={embeddingModel}
                  onChange={(event) => setEmbeddingModel(event.target.value)}
                  placeholder="nomic-embed-text"
                  required
                />
              </Field>
            ) : null}
            <div className="row">
              <Button type="submit" loading={busy}>
                {editing ? "Save changes" : "Create knowledge base"}
              </Button>
              {editing ? (
                <Button type="button" variant="ghost" onClick={resetForm}>
                  Cancel
                </Button>
              ) : null}
            </div>
          </form>
        </Card>
      </div>

      {selectedId ? (
        <section className="knowledge-workspace">
          <Card
            title={active ? active.name : "Knowledge base"}
            description={
              active
                ? `${active.mode === "vector" ? "Semantic" : "Keyword"} search · ${active.document_count} documents · ${active.chunk_count} chunks`
                : "Loading the selected knowledge base…"
            }
            padded={false}
          >
            {selected.error ? (
              <div style={{ padding: 16 }}>
                <ErrorBlock message={selected.error} onRetry={selected.reload} />
              </div>
            ) : selected.loading && !active ? (
              <LoadingBlock rows={4} />
            ) : active ? (
              <div className="knowledge-workspace-body">
                <form className="stack knowledge-upload" onSubmit={addDocument}>
                  <div className="knowledge-section-title">
                    <div>
                      <h3>Add a document</h3>
                      <p className="small muted">
                        Paste text or load a text file. PDFs and scanned images are not parsed yet.
                      </p>
                    </div>
                    <input
                      ref={fileRef}
                      type="file"
                      accept={TEXT_EXTENSIONS.join(",")}
                      style={{ display: "none" }}
                      onChange={(event) => {
                        const file = event.target.files?.[0];
                        if (file) readFile(file);
                      }}
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      icon={<Icon name="plus" size={14} />}
                      onClick={() => fileRef.current?.click()}
                    >
                      Load text file
                    </Button>
                  </div>
                  {docError ? <InlineError message={docError} /> : null}
                  <div className="form-grid">
                    <Field label="Document name" htmlFor="doc-name" required>
                      <Input
                        id="doc-name"
                        value={docName}
                        onChange={(event) => setDocName(event.target.value)}
                        placeholder="refund-policy.md"
                        required
                      />
                    </Field>
                    <Field label="Characters" htmlFor="doc-count">
                      <Input id="doc-count" value={docText.length} readOnly />
                    </Field>
                  </div>
                  <Field label="Content" htmlFor="doc-text" required>
                    <Textarea
                      id="doc-text"
                      className="textarea-mono"
                      rows={10}
                      value={docText}
                      onChange={(event) => setDocText(event.target.value)}
                      placeholder="Paste the document text here…"
                      required
                    />
                  </Field>
                  <div className="row">
                    <Button type="submit" loading={docBusy} disabled={!docText.trim()}>
                      Index document
                    </Button>
                  </div>
                </form>

                <div className="knowledge-documents">
                  <div className="knowledge-section-title">
                    <h3>Documents</h3>
                    <span className="small faint">{active.documents?.length ?? 0}</span>
                  </div>
                  {(active.documents?.length ?? 0) === 0 ? (
                    <p className="small muted">
                      No documents yet. Add one on the left; the agent will retrieve from it immediately.
                    </p>
                  ) : (
                    <ul className="list-plain">
                      {active.documents?.map((document) => (
                        <li className="list-item" key={document.id}>
                          <div>
                            <p className="list-item-title">{document.name}</p>
                            <p className="list-item-meta">
                              {document.chunk_count} chunks · {Math.round(document.size_bytes / 1024)} KB
                            </p>
                          </div>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => void removeDocument(document.id, document.name)}
                          >
                            Remove
                          </Button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            ) : null}
          </Card>

          <Card
            title="Test retrieval"
            description="This runs the exact search a Retrieval node uses. Check the chunks and scores before connecting the agent."
          >
            <form className="stack" onSubmit={runSearch}>
              <Field label="Question" htmlFor="kb-query" required>
                <Input
                  id="kb-query"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="What is the refund window for annual plans?"
                  required
                />
              </Field>
              {searchError ? <InlineError message={searchError} /> : null}
              <div className="row">
                <Button type="submit" loading={searchBusy} disabled={!query.trim()}>
                  Search
                </Button>
                <span className="small faint">Top 5 chunks, newest index</span>
              </div>
            </form>
            {search ? (
              search.results.length === 0 ? (
                <p className="small muted" style={{ marginTop: 16 }}>
                  No chunks matched. Add a document or rephrase the question.
                </p>
              ) : (
                <ol className="knowledge-results">
                  {search.results.map((result) => (
                    <li key={result.chunk_id}>
                      <div className="knowledge-result-head">
                        <strong>{result.document_name}</strong>
                        <span className={`knowledge-score ${result.score >= 0.4 ? "is-good" : ""}`}>
                          {(result.score * 100).toFixed(0)}%
                        </span>
                      </div>
                      <p>{result.content.slice(0, 600)}</p>
                    </li>
                  ))}
                </ol>
              )
            ) : null}
          </Card>
        </section>
      ) : null}
    </div>
  );
}
