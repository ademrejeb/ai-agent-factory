"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  ReactFlow,
  type Connection,
  type Edge,
  type EdgeChange,
  type NodeChange,
  type OnConnect,
  type OnEdgesChange,
  type OnNodesChange,
  type ReactFlowInstance,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";

import { LocalGraphNode, type LocalFlowNode } from "@/components/graph/LocalGraphNode";
import {
  connectionProblem,
  nextEdgeId,
  type LocalGraph,
  type LocalNode,
} from "@/lib/local-graph";

const nodeTypes = { localGraphNode: LocalGraphNode };

type NodeSize = { width: number; height: number };

function sameSize(
  a: { width?: number; height?: number } | undefined,
  b: NodeSize | undefined,
): boolean {
  if (a === b) return true;
  if (!a || !b) return false;
  return a.width === b.width && a.height === b.height;
}

interface LocalGraphCanvasProps {
  graph: LocalGraph;
  readOnly: boolean;
  selectedId: string | null;
  onSelect: (nodeId: string | null) => void;
  onChange: (patch: Partial<Pick<LocalGraph, "nodes" | "edges">>) => void;
  onNotice: (message: string) => void;
  /** Node to center after it is added from the palette. */
  revealNodeId?: string | null;
}

export function LocalGraphCanvas({
  graph,
  readOnly,
  selectedId,
  onSelect,
  onChange,
  onNotice,
  revealNodeId = null,
}: LocalGraphCanvasProps) {
  const [sizes, setSizes] = useState<Record<string, NodeSize>>({});
  const [instance, setInstance] = useState<ReactFlowInstance<LocalFlowNode, Edge> | null>(null);
  const nodeCache = useRef<Map<string, LocalFlowNode>>(new Map());
  const revealed = useRef<string | null>(null);
  const fittedCount = useRef(0);

  const nodes = useMemo<LocalFlowNode[]>(() => {
    const nextCache = new Map<string, LocalFlowNode>();
    const list = Object.values(graph.nodes).map((node) => {
      const size = sizes[node.id];
      const selected = node.id === selectedId;
      const cached = nodeCache.current.get(node.id);
      if (
        cached &&
        cached.data.node === node &&
        cached.position.x === node.position.x &&
        cached.position.y === node.position.y &&
        cached.selected === selected &&
        sameSize(cached.measured, size)
      ) {
        nextCache.set(node.id, cached);
        return cached;
      }
      const next: LocalFlowNode = {
        id: node.id,
        type: "localGraphNode",
        position: node.position,
        measured: size,
        selected,
        data: { node },
      };
      nextCache.set(node.id, next);
      return next;
    });
    nodeCache.current = nextCache;
    return list;
  }, [graph.nodes, selectedId, sizes]);

  const edges = useMemo<Edge[]>(
    () =>
      graph.edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? undefined,
        label: edge.sourceHandle ?? undefined,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
      })),
    [graph.edges],
  );

  const onNodesChange: OnNodesChange<LocalFlowNode> = useCallback(
    (changes: NodeChange<LocalFlowNode>[]) => {
      const removed: string[] = [];
      const nextSizes: Record<string, NodeSize> = {};
      let nodes = graph.nodes;
      let changed = false;

      for (const change of changes) {
        if (change.type === "position" && change.position) {
          const current = nodes[change.id];
          if (!current) continue;
          if (
            current.position.x !== change.position.x ||
            current.position.y !== change.position.y
          ) {
            nodes = {
              ...nodes,
              [change.id]: { ...current, position: change.position },
            };
            changed = true;
          }
        } else if (change.type === "dimensions" && change.dimensions) {
          nextSizes[change.id] = {
            width: change.dimensions.width,
            height: change.dimensions.height,
          };
        } else if (change.type === "remove") {
          removed.push(change.id);
        }
      }

      if (Object.keys(nextSizes).length > 0) {
        setSizes((current) => {
          let dirty = false;
          const next = { ...current };
          for (const [id, size] of Object.entries(nextSizes)) {
            if (!sameSize(current[id], size)) {
              next[id] = size;
              dirty = true;
            }
          }
          return dirty ? next : current;
        });
      }

      if (removed.length > 0) {
        const nextNodes = { ...nodes };
        for (const id of removed) delete nextNodes[id];
        const nextEdges = graph.edges.filter(
          (edge) => !removed.includes(edge.source) && !removed.includes(edge.target),
        );
        onChange({ nodes: nextNodes, edges: nextEdges });
        if (selectedId && removed.includes(selectedId)) onSelect(null);
        return;
      }
      if (changed) onChange({ nodes });
    },
    [graph.nodes, graph.edges, onChange, onSelect, selectedId],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const removed: string[] = [];
      for (const change of changes) {
        if (change.type === "remove") removed.push(change.id);
      }
      if (removed.length > 0) {
        onChange({ edges: graph.edges.filter((edge) => !removed.includes(edge.id)) });
      }
    },
    [graph.edges, onChange],
  );

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      const rawHandle = connection.sourceHandle;
      const handle =
        rawHandle === "true" ||
        rawHandle === "false" ||
        rawHandle === "pass" ||
        rawHandle === "fail"
          ? rawHandle
          : null;
      const problem = connectionProblem(graph, connection.source, connection.target, handle);
      if (problem) {
        onNotice(problem);
        return;
      }
      onChange({
        edges: [
          ...graph.edges,
          {
            id: nextEdgeId(graph, connection.source, connection.target),
            source: connection.source,
            target: connection.target,
            sourceHandle: handle,
          },
        ],
      });
    },
    [graph, onChange, onNotice],
  );

  const handleNodeClick = useCallback(
    (_event: ReactMouseEvent, node: LocalFlowNode) => onSelect(node.id),
    [onSelect],
  );

  const handleKeyDown = useCallback(
    (event: ReactKeyboardEvent<HTMLDivElement>) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      const target = event.target as HTMLElement | null;
      const nodeElement = target?.closest?.(".react-flow__node");
      const id = nodeElement?.getAttribute("data-id");
      if (!id) return;
      event.preventDefault();
      onSelect(id);
    },
    [onSelect],
  );

  useEffect(() => {
    if (!instance || !revealNodeId) return;
    if (revealed.current === revealNodeId) return;
    const size = sizes[revealNodeId];
    const node = graph.nodes[revealNodeId];
    if (!size || !node) return;
    revealed.current = revealNodeId;
    const zoom = Math.min(Math.max(instance.getZoom(), 0.65), 1);
    void instance.setCenter(
      node.position.x + size.width / 2,
      node.position.y + size.height / 2,
      { zoom, duration: 320 },
    );
  }, [graph.nodes, instance, revealNodeId, sizes]);

  useEffect(() => {
    if (!instance) return;
    const count = Object.keys(graph.nodes).length;
    if (count === 0 || fittedCount.current === count) return;
    fittedCount.current = count;
    const timer = window.setTimeout(() => {
      void instance.fitView({ padding: 0.25, maxZoom: 1.1, duration: 220 });
    }, 80);
    return () => window.clearTimeout(timer);
  }, [graph.nodes, instance]);

  return (
    <div className="wf-canvas-wrap graph-canvas" onKeyDown={handleKeyDown}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={setInstance}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={handleNodeClick}
        onPaneClick={() => onSelect(null)}
        multiSelectionKeyCode={null}
        fitView
        fitViewOptions={{ padding: 0.25, maxZoom: 1.1 }}
        minZoom={0.2}
        maxZoom={1.6}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
        elementsSelectable
        defaultEdgeOptions={{ type: "smoothstep" }}
        deleteKeyCode={readOnly ? null : ["Backspace", "Delete"]}
      >
        <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#223041" />
        <Controls showInteractive={false} position="bottom-right" />
        <MiniMap
          pannable
          zoomable
          position="bottom-left"
          nodeColor={(node) => {
            const data = node.data as { node?: LocalNode };
            const type = data.node?.type;
            if (type === "input") return "#3fb950";
            if (type === "agent") return "#22d3ee";
            if (type === "llm") return "#4d7cfe";
            if (type === "tool") return "#f472b6";
            if (type === "guardrail") return "#f97316";
            if (type === "condition") return "#fbbf24";
            if (type === "http") return "#c084fc";
            return "#64748b";
          }}
          maskColor="rgba(8, 12, 17, 0.78)"
        />
      </ReactFlow>

      <div className="wf-canvas-legend" aria-hidden="true">
        <span>
          <strong>{Object.keys(graph.nodes).length}</strong> nodes
        </span>
        <span>
          <strong>{graph.edges.length}</strong> connections
        </span>
      </div>

      {Object.keys(graph.nodes).length === 0 ? (
        <div className="wf-canvas-empty">
          <p className="wf-canvas-empty-title">This graph is empty</p>
          <p className="small muted">Add an input node from the palette to start building.</p>
        </div>
      ) : null}
    </div>
  );
}
