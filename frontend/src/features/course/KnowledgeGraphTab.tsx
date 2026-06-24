import { useMemo, useState, useCallback } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import dagre from "@dagrejs/dagre";
import { GitBranch, RefreshCw, X, BookOpen, Link2 } from "lucide-react";
import { useKnowledgeGraph, type KGNode, type KGEdge } from "./useKnowledgeGraph";
import { foxCopy } from "../../shared/fox-copy";
import { api } from "../../shared/api";
import type { KC } from "../../shared/types";

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

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedKC, setSelectedKC] = useState<KC | null>(null);
  const [kcLoading, setKcLoading] = useState(false);

  const handleNodeClick = useCallback((_: unknown, node: Node) => {
    setKcLoading(true);
    setDrawerOpen(true);
    setSelectedKC(null);
    // Fetch KC details from backend
    api.get<KC>(`/courses/${courseId}/knowledge-graph/nodes/${node.id}`)
      .then((kc) => setSelectedKC(kc))
      .catch(() => setSelectedKC(null))
      .finally(() => setKcLoading(false));
  }, [courseId]);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedKC(null);
  }, []);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return buildLayout(data.nodes, data.edges);
  }, [data]);

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
    <div className="flex gap-4">
      {/* 知识图谱 */}
      <div className="flex-1 space-y-3">
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
        </div>
        <div className="border border-gray-200 rounded-xl bg-white" style={{ height: 520 }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background />
            <Controls />
          </ReactFlow>
        </div>
      </div>

      {/* KC 详情 Drawer */}
      {drawerOpen && (
        <div className="w-80 shrink-0 bg-white border border-gray-200 rounded-xl shadow-lg overflow-hidden fox-fade-in">
          <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100 bg-gray-50">
            <h3 className="text-sm font-bold text-midnightCharcoal">知识详情</h3>
            <button onClick={closeDrawer} className="p-1 rounded hover:bg-gray-200 transition-colors text-gray-400">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="p-4 overflow-y-auto" style={{ maxHeight: 460 }}>
            {kcLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="w-5 h-5 border-2 border-foxAmber border-t-transparent rounded-full animate-spin" />
              </div>
            ) : selectedKC ? (
              <div className="space-y-4">
                <div>
                  <h4 className="text-lg font-bold text-midnightCharcoal">{selectedKC.name}</h4>
                  <p className="text-xs text-gray-400 mt-1">Bloom: {selectedKC.bloom_level}</p>
                </div>
                {selectedKC.definition && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1">定义</p>
                    <p className="text-sm text-gray-700 leading-relaxed">{selectedKC.definition}</p>
                  </div>
                )}
                {selectedKC.formula && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1">公式</p>
                    <p className="text-sm text-gray-700 font-mono bg-gray-50 rounded-lg px-3 py-2">{selectedKC.formula}</p>
                  </div>
                )}
                {selectedKC.prerequisites && selectedKC.prerequisites.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                      <Link2 className="w-3 h-3" /> 先修概念
                    </p>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedKC.prerequisites.map((p, i) => (
                        <span key={i} className="text-xs px-2 py-0.5 bg-foxAmber/10 text-foxAmber rounded-full">{typeof p === 'string' ? p : p.prerequisite_kc_id}</span>
                      ))}
                    </div>
                  </div>
                )}
                {selectedKC.examples && selectedKC.examples.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-gray-500 mb-1 flex items-center gap-1">
                      <BookOpen className="w-3 h-3" /> 例子
                    </p>
                    <ul className="space-y-1">
                      {selectedKC.examples.map((ex, i) => (
                        <li key={i} className="text-sm text-gray-600">• {ex}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-8">无法加载详情</p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
