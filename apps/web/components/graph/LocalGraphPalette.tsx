"use client";

import { Button } from "@/components/ui/Button";
import { Icon } from "@/components/ui/Icon";
import { NODE_META, NODE_ORDER, type LocalNodeType } from "@/lib/local-graph";

interface LocalGraphPaletteProps {
  counts: Record<LocalNodeType, number>;
  disabled: boolean;
  onAdd: (type: LocalNodeType) => void;
}

export function LocalGraphPalette({ counts, disabled, onAdd }: LocalGraphPaletteProps) {
  return (
    <aside className="wf-panel wf-palette" aria-label="Node library">
      <header className="wf-panel-head">
        <div>
          <h2>Node library</h2>
          <p>Add a node, then connect it on the canvas.</p>
        </div>
        <span className="wf-panel-badge">{NODE_ORDER.length}</span>
      </header>

      <div className="wf-palette-list">
        {NODE_ORDER.map((type) => {
          const meta = NODE_META[type];
          const isInputTaken = type === "input" && counts.input > 0;
          return (
            <button
              key={type}
              type="button"
              className="wf-palette-item"
              disabled={disabled || isInputTaken}
              onClick={() => onAdd(type)}
              title={isInputTaken ? "A graph has exactly one input node." : meta.description}
            >
              <span className={`graph-palette-icon graph-type-${meta.tone}`}>
                <Icon name={meta.icon} size={15} />
              </span>
              <span className="wf-palette-item-main">
                <span className="wf-palette-item-name">
                  {meta.label}
                  {counts[type] > 0 ? <span className="wf-mini-chip">{counts[type]}</span> : null}
                </span>
                <span className="wf-palette-item-desc">{meta.description}</span>
              </span>
              <span className="wf-palette-add" aria-hidden="true">
                <Icon name={isInputTaken ? "check" : "plus"} size={14} />
              </span>
            </button>
          );
        })}
      </div>

      <footer className="wf-palette-foot">
        <p className="small faint" style={{ marginBottom: 10 }}>
          Graphs stay acyclic and never merge. Agent nodes can call several tools in a bounded loop;
          conditions and guardrails split into two branches that each end at an output.
        </p>
        {counts.condition > 0 ? (
          <Button size="sm" variant="ghost" disabled={disabled} onClick={() => onAdd("output")}>
            <Icon name="plus" size={13} />
            <span>Add branch output</span>
          </Button>
        ) : null}
      </footer>
    </aside>
  );
}
