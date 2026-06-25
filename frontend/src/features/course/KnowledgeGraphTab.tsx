import { useMemo, useState, useCallback } from "react";
import { ReactFlow, Background, Controls, type Node, type Edge } from "reactflow";
import "reactflow/dist/style.css";
import dagre from "@dagrejs/dagre";
import { GitBranch, RefreshCw, BookOpen, Link2, Lightbulb, AlertTriangle, FileText, MessageCircle } from "lucide-react";
import { useKnowledgeGraph, type KGNode, type KGEdge } from "./useKnowledgeGraph";
import { foxCopy } from "../../shared/fox-copy";
import { api } from "../../shared/api";
import type { KC } from "../../shared/types";
import { Drawer } from "../../components/ui/Drawer";
import { Spinner } from "../../components/ui/Spinner";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import MarkdownRenderer from "./MarkdownRenderer";

interface KnowledgeGraphTabProps {
  courseId: string;
  onAskAboutConcept?: (concept: string) => void;
}

const IMPORTANCE_BORDER: Record<KGNode["importance"], string> = {
  high: "border-l-4 border-red-400",
  medium: "border-l-4 border-foxAmber",
  low: "border-l-4 border-slate-300",
};

const IMPORTANCE_DOT: Record<KGNode["importance"], string> = {
  high: "bg-red-400",
  medium: "bg-foxAmber",
  low: "bg-slate-300",
};

const IMPORTANCE_LABEL: Record<KGNode["importance"], string> = {
  high: "高频考点",
  medium: "中频",
  low: "低频",
};

const NODE_WIDTH = 200;
const NODE_HEIGHT = 56;

const EMPTY_NODE_TYPES = {};
const EMPTY_EDGE_TYPES = {};

function buildLayout(
  nodes: KGNode[],
  edges: KGEdge[],
): { nodes: Node[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "LR", nodesep: 28, ranksep: 70 });

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
      data: { label: n.label, importance: n.importance },
      style: {
        background: "#ffffff",
        color: "#0f172a",
        border: "1px solid #e2e8f0",
        borderRadius: 12,
        padding: "10px 14px",
        fontSize: 13,
        fontWeight: 600,
        width: NODE_WIDTH,
        boxShadow: "0 2px 8px -2px rgba(0,0,0,0.08)",
      },
      className: `!bg-white !border-slate-200 hover:!shadow-md hover:!scale-[1.02] transition-all duration-200 ${IMPORTANCE_BORDER[n.importance]}`,
    };
  });

  const flowEdges: Edge[] = edges.map((e, i) => ({
    id: `${e.source}-${e.target}-${i}`,
    source: e.source,
    target: e.target,
    type: "smoothstep",
    animated: false,
    style: { stroke: "#94a3b8", strokeWidth: Math.max(1.5, e.strength * 2.5) },
  }));

  return { nodes: positioned, edges: flowEdges };
}

export default function KnowledgeGraphTab({ courseId, onAskAboutConcept }: KnowledgeGraphTabProps) {
  const { data, loading, error, refetch } = useKnowledgeGraph(courseId);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedKC, setSelectedKC] = useState<KC | null>(null);
  const [kcLoading, setKcLoading] = useState(false);

  const handleNodeClick = useCallback((_: unknown, node: Node) => {
    setKcLoading(true);
    setDrawerOpen(true);
    setSelectedKC(null);
    api.get<KC>(`/courses/${courseId}/knowledge-graph/nodes/${node.id}`)
      .then((kc) => setSelectedKC(kc))
      .catch(() => setSelectedKC(null))
      .finally(() => setKcLoading(false));
  }, [courseId]);

  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    setSelectedKC(null);
  }, []);

  const handlePrereqClick = useCallback((prereqId: string) => {
    setKcLoading(true);
    setSelectedKC(null);
    api.get<KC>(`/courses/${courseId}/knowledge-graph/nodes/${prereqId}`)
      .then((kc) => setSelectedKC(kc))
      .catch(() => setSelectedKC(null))
      .finally(() => setKcLoading(false));
  }, [courseId]);

  const handleAskFox = useCallback(() => {
    if (selectedKC && onAskAboutConcept) {
      onAskAboutConcept(selectedKC.name);
      closeDrawer();
    }
  }, [selectedKC, onAskAboutConcept, closeDrawer]);

  const { nodes, edges } = useMemo(() => {
    if (!data) return { nodes: [], edges: [] };
    return buildLayout(data.nodes, data.edges);
  }, [data]);

  const bloomBadgeVariant = (bloom: string) => {
    const b = bloom.toLowerCase();
    if (["create", "evaluate"].includes(b)) return "error" as const;
    if (["analyze", "apply"].includes(b)) return "amber" as const;
    return "info" as const;
  };

  const renderFormula = (formula: string) => {
    if (!formula) return null;
    const hasMath = /\$[^$]+\$/.test(formula);
    if (hasMath) {
      return <MarkdownRenderer content={formula} light />;
    }
    return (
      <code className="text-sm bg-slate-100 text-slate-700 px-3 py-2 rounded-lg block font-mono">
        {formula}
      </code>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="flex flex-col items-center gap-3">
          <Spinner size="lg" />
          <p className="text-sm text-slate-500">加载知识图谱...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="text-center py-16">
        <p className="text-red-500 text-sm mb-4">{foxCopy.errors.loadFailed}</p>
        <Button variant="secondary" onClick={refetch}>
          <RefreshCw className="w-4 h-4" />
          {foxCopy.errors.retry}
        </Button>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="text-center py-20">
        <div className="inline-flex p-4 rounded-2xl bg-slate-100 mb-4">
          <GitBranch className="w-12 h-12 text-slate-400" />
        </div>
        <p className="text-lg font-medium text-slate-600 mb-2">暂无知识图谱</p>
        <p className="text-sm text-slate-400">先上传材料并构建 Wiki 骨架</p>
      </div>
    );
  }

  return (
    <div className="h-full p-4">
      <Card padding="none" shadow="soft" className="h-full rounded-2xl overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h3 className="font-semibold text-midnightCharcoal">知识图谱</h3>
          <div className="flex items-center gap-4 text-xs">
            <span className="font-medium text-slate-500">图例:</span>
            {(["high", "medium", "low"] as const).map((level) => (
              <span key={level} className="flex items-center gap-1.5">
                <span className={`inline-block w-3 h-3 rounded ${IMPORTANCE_DOT[level]}`} />
                <span className="text-slate-600">{IMPORTANCE_LABEL[level]}</span>
              </span>
            ))}
          </div>
        </div>
        <div className="bg-slate-50/50" style={{ height: "calc(100% - 65px)" }}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodeClick={handleNodeClick}
            fitView
            proOptions={{ hideAttribution: true }}
            nodesDraggable={false}
            nodeTypes={EMPTY_NODE_TYPES}
            edgeTypes={EMPTY_EDGE_TYPES}
          >
            <Background color="#e2e8f0" gap={20} size={1} />
            <Controls className="!bg-white !rounded-lg !shadow-soft !border-slate-200" />
          </ReactFlow>
        </div>
      </Card>

      <Drawer
        open={drawerOpen}
        onClose={closeDrawer}
        title="概念详情"
        width={420}
      >
        <div className="p-5">
          {kcLoading ? (
            <div className="flex items-center justify-center py-16">
              <Spinner size="lg" />
            </div>
          ) : selectedKC ? (
            <div className="space-y-5">
              <div>
                <h2 className="text-xl font-bold text-midnightCharcoal leading-tight">
                  {selectedKC.name}
                </h2>
                {selectedKC.bloom_level && (
                  <div className="mt-2">
                    <Badge variant={bloomBadgeVariant(selectedKC.bloom_level)} size="sm">
                      认知维度: {selectedKC.bloom_level}
                    </Badge>
                  </div>
                )}
              </div>

              {selectedKC.definition && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <BookOpen className="w-4 h-4 text-foxAmber" />
                    <span className="text-sm font-semibold text-slate-700">定义</span>
                  </div>
                  <div className="pl-6">
                    <p className="text-sm text-slate-600 leading-relaxed">
                      {selectedKC.definition}
                    </p>
                  </div>
                </div>
              )}

              {selectedKC.formula && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-base">📐</span>
                    <span className="text-sm font-semibold text-slate-700">公式</span>
                  </div>
                  <div className="pl-6">
                    {renderFormula(selectedKC.formula)}
                  </div>
                </div>
              )}

              {selectedKC.intuition && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Lightbulb className="w-4 h-4 text-amber-500" />
                    <span className="text-sm font-semibold text-slate-700">直觉理解</span>
                  </div>
                  <div className="pl-6">
                    <p className="text-sm text-slate-600 leading-relaxed bg-amber-50 rounded-lg p-3 border border-amber-100">
                      {selectedKC.intuition}
                    </p>
                  </div>
                </div>
              )}

              {selectedKC.common_mistakes && selectedKC.common_mistakes.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <AlertTriangle className="w-4 h-4 text-red-500" />
                    <span className="text-sm font-semibold text-red-600">常见错误</span>
                  </div>
                  <div className="pl-6">
                    <ul className="space-y-1.5">
                      {selectedKC.common_mistakes.map((m, i) => (
                        <li key={i} className="text-sm text-red-600 flex items-start gap-2">
                          <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-red-400 shrink-0" />
                          {m}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {selectedKC.examples && selectedKC.examples.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-blue-500" />
                    <span className="text-sm font-semibold text-slate-700">例子</span>
                  </div>
                  <div className="pl-6">
                    <ul className="space-y-1.5">
                      {selectedKC.examples.map((ex, i) => (
                        <li key={i} className="text-sm text-slate-600 flex items-start gap-2">
                          <span className="text-foxAmber font-medium shrink-0">{i + 1}.</span>
                          {ex}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {selectedKC.prerequisites && selectedKC.prerequisites.length > 0 && (
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Link2 className="w-4 h-4 text-slate-500" />
                    <span className="text-sm font-semibold text-slate-700">先修概念</span>
                  </div>
                  <div className="pl-6 flex flex-wrap gap-2">
                    {selectedKC.prerequisites.map((p, i) => (
                      <button
                        key={i}
                        onClick={() => handlePrereqClick(p.prerequisite_kc_id)}
                        className="text-xs px-3 py-1.5 bg-slate-100 hover:bg-foxAmber/10 text-slate-700 hover:text-foxAmber rounded-full transition-colors border border-slate-200 hover:border-foxAmber/30"
                      >
                        {p.prerequisite_kc_id}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {onAskAboutConcept && (
                <div className="pt-4 border-t border-slate-100">
                  <Button
                    onClick={handleAskFox}
                    className="w-full rounded-xl"
                    size="lg"
                  >
                    <MessageCircle className="w-4 h-4" />
                    去问狐狸关于这个概念
                  </Button>
                </div>
              )}
            </div>
          ) : (
            <div className="text-center py-12">
              <p className="text-sm text-slate-400">无法加载概念详情</p>
            </div>
          )}
        </div>
      </Drawer>
    </div>
  );
}
