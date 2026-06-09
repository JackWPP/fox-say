import { useState, useEffect, useCallback } from "react";
import { api } from "../../shared/api";

export type Importance = "high" | "medium" | "low";
export type CognitiveDimension =
  | "factual"
  | "conceptual"
  | "procedural_skill"
  | "procedural_principle"
  | "metacognitive";
export type EdgeType = "prerequisite" | "related";

export interface KGNode {
  id: string;
  label: string;
  chapter_id: string;
  mastery: number;
  importance: Importance;
  cognitive_dimension: CognitiveDimension;
}

export interface KGEdge {
  source: string;
  target: string;
  strength: number;
  edge_type: EdgeType;
}

export interface KnowledgeGraphResponse {
  course_id: string;
  nodes: KGNode[];
  edges: KGEdge[];
  layout_hint?: string;
}

export interface UseKnowledgeGraphResult {
  data: KnowledgeGraphResponse | null;
  loading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useKnowledgeGraph(courseId: string): UseKnowledgeGraphResult {
  const [data, setData] = useState<KnowledgeGraphResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refetch = useCallback(async () => {
    if (!courseId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<KnowledgeGraphResponse>(
        `/courses/${courseId}/knowledge-graph`,
      );
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to fetch knowledge graph");
    } finally {
      setLoading(false);
    }
  }, [courseId]);

  useEffect(() => {
    refetch();
  }, [refetch]);

  return { data, loading, error, refetch };
}
