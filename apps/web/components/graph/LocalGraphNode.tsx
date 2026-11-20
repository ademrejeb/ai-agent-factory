"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { Icon } from "@/components/ui/Icon";
import { NODE_META, nodeSummary, type LocalNode } from "@/lib/local-graph";

export interface LocalNodeData extends Record<string, unknown> {
  node: LocalNode;
}

export type LocalFlowNode = Node<LocalNodeData, "localGraphNode">;

export function LocalGraphNode({ data, selected }: NodeProps<LocalFlowNode>) {
  const { node } = data;
  const meta = NODE_META[node.type];
  const isCondition = node.type === "condition";
  const isGuardrail = node.type === "guardrail";

  return (
    <div
      className={`graph-node graph-node-${meta.tone} ${selected ? "is-selected" : ""}`}
      title={meta.description}
    >
      {node.type !== "input" ? (
        <Handle type="target" position={Position.Left} className="graph-handle" />
      ) : null}

      <header className="graph-node-head">
        <span className="graph-node-icon">
          <Icon name={meta.icon} size={15} />
        </span>
        <div className="graph-node-heading">
          <p className="graph-node-title" title={node.name}>
            {node.name}
          </p>
          <p className="graph-node-type mono">
            {meta.label} · {node.id}
          </p>
        </div>
      </header>

      <p className="graph-node-summary">{nodeSummary(node)}</p>

      <footer className="graph-node-foot">
        <span className="graph-node-chip">{node.type}</span>
        {isCondition ? (
          <>
            <span className="graph-node-chip graph-chip-true">true</span>
            <span className="graph-node-chip graph-chip-false">false</span>
          </>
        ) : null}
        {isGuardrail ? (
          <>
            <span className="graph-node-chip graph-chip-true">pass</span>
            <span className="graph-node-chip graph-chip-false">fail</span>
          </>
        ) : null}
        {node.type === "agent" ? <span className="graph-node-chip">tool loop</span> : null}
        {node.type === "http" ? <span className="graph-node-chip">external</span> : null}
      </footer>

      {node.type !== "output" ? (
        isCondition || isGuardrail ? (
          <>
            <Handle
              id={isCondition ? "true" : "pass"}
              type="source"
              position={Position.Right}
              className="graph-handle graph-handle-true"
              style={{ top: "34%" }}
            />
            <Handle
              id={isCondition ? "false" : "fail"}
              type="source"
              position={Position.Right}
              className="graph-handle graph-handle-false"
              style={{ top: "72%" }}
            />
          </>
        ) : (
          <Handle type="source" position={Position.Right} className="graph-handle" />
        )
      ) : null}
    </div>
  );
}
