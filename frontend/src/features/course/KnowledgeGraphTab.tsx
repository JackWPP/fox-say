import { useMemo } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import dagre from "@dagrejs/dagre";
import { GitBranch, RefreshCw } from "lucide-react";
import { useKnowledgeGraph, type KGNode, type KGEdge } from "./useKnowledgeGraph";
import { foxCopy } from "../../shared/fox-copy";

interface KnowledgeGraphTabProps {
  courseId: string;
}

const IMPORTANCE_COLOR: Record<KGNode["importance"], string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#94a3b8",
};

const NODE_WIDTH = 180;
const NODE_HEIGHT = 48;

function buildLayout(
  nodes: KGNode[],
  edges: KGEdge[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 24, ranksep: 60 });

  for (const n of nodes) {
    g.setNode(n.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }
  for (const e of edges) {
    g.setEdge(e.source, e.target);
  }
  dagre.layout(g);

  const positioned: Node[] = nodes.map((n) => {
    const pos = g.node(n.id);
    return {
      id: n.id,
      type: "default",
      position: { x: pos.x - NODE_WIDTH / 2, y: pos.y - NODE_HEIGHT / 2 },
      data: { label: `${n.label} · ${n.importance}` },
      style: {
        background: IMPORTANCE_COLOR[n.importance],
        color: "#fff",
        border: "1px solid rgba(0,0,0,0.1)",
        borderRadius: 8,
        padding: "6px 10px",
        fontSize: 12,
        fontWeight: 600,
        width: NODE_WIDTH,
      },
    };
  });

  const flowEdges: Edge[] = edges.map((e, i) => ({
    id: `${e.source}-${e.target}-${i}`,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#94a3b8", strokeWidth: Math.max(1, e.strength * 2) },
  }));

  return { nodes: positioned, edges: flowEdges };
}

export default function KnowledgeGraphTab({ courseId }: KnowledgeGraphTabProps) {
  const { data, loading, error, refetch } = useKnowledgeGraph(courseId);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return buildLayout(data.nodes, data.edges);
  }, [data]);

  const onNodeClick = (_: unknown, node: Node) => {
    // MVP 占位:HEC-3 — 行为可见(console + alert),后续接详情抽屉
    // eslint-disable-next-line no-console
    console.log("[KG] clicked node:", node.id, node.data);
    alert(`知识节点:${node.data?.label ?? node.id}`);
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-6 h-6 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-red-500 text-sm mb-3">{foxCopy.errors.loadFailed}</p>
        <button
          onClick={refetch}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-500 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          {foxCopy.errors.retry}
        </button>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="text-center py-16 text-gray-400">
        <GitBranch className="w-12 h-12 mx-auto mb-3 opacity-40" />
        <p className="text-lg">暂无知识图谱</p>
        <p className="text-xs mt-2 text-gray-300">先上传材料并构建 Wiki 骨架</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-4 text-xs text-gray-600">
        <span className="font-semibold text-midnightCharcoal">图例</span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ background: IMPORTANCE_COLOR.high }} />
          高频考点
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ background: IMPORTANCE_COLOR.medium }} />
          中频
        </span>
        <span className="flex items-center gap-1">
          <span className="inline-block w-3 h-3 rounded" style={{ background: IMPORTANCE_COLOR.low }} />
          低频
        </span>
        <span className="ml-auto text-gray-400">点击节点查看(占位)</span>
      </div>
      <div className="border border-gray-200 rounded-xl bg-white" style={{ height: 520 }}>
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodeClick={onNodeClick}
          fitView
          proOptions={{ hideAttribution: true }}
        >
          <Background />
          <Controls />
        </ReactFlow>
      </div>
    </div>
  );
}
