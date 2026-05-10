import { useEffect, useRef, useCallback } from "react";
import * as d3 from "d3";
import type { CourseSkeleton } from "../../shared/types";

interface SkeletonTreeProps {
  skeleton: CourseSkeleton;
  onConceptClick?: (concept: string) => void;
}

interface GraphNode extends d3.SimulationNodeDatum {
  id: string;
  label: string;
  nodeType: "concept" | "chapter" | "difficulty";
  importance: string;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  relation: string;
}

export default function SkeletonTree({ skeleton, onConceptClick }: SkeletonTreeProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  const ensureNode = (id: string, label: string, type: GraphNode["nodeType"], importance: string, nodes: GraphNode[], nodeIds: Set<string>) => {
    if (!nodeIds.has(id)) {
      nodeIds.add(id);
      nodes.push({ id, label, nodeType: type, importance });
    }
  };

  const buildGraph = useCallback((): { nodes: GraphNode[]; links: GraphLink[] } => {
    const nodes: GraphNode[] = [];
    const links: GraphLink[] = [];
    const nodeIds = new Set<string>();

    // Create concept nodes from chapter.key_concepts FIRST (before links)
    for (const ch of skeleton.chapters) {
      for (const concept of ch.key_concepts) {
        const cid = `concept_${concept.replace(/\s+/g, "_").toLowerCase()}`;
        ensureNode(cid, concept, "concept", ch.importance, nodes, nodeIds);
      }
    }

    // Chapter nodes
    for (const ch of skeleton.chapters) {
      ensureNode(ch.id, ch.title, "chapter", ch.importance, nodes, nodeIds);
      // Link chapter to its key concepts (nodes now guaranteed to exist)
      for (const concept of ch.key_concepts) {
        const cid = `concept_${concept.replace(/\s+/g, "_").toLowerCase()}`;
        links.push({ source: ch.id, target: cid, relation: "contains" });
      }
    }

    // Core concept nodes (may add to existing)
    for (const concept of skeleton.core_concepts || []) {
      const cid = `concept_${concept.replace(/\s+/g, "_").toLowerCase()}`;
      ensureNode(cid, concept, "concept", "high", nodes, nodeIds);
    }

    // Difficulty area nodes
    for (const area of skeleton.difficulty_areas || []) {
      const label = area.length > 30 ? area.slice(0, 30) + "..." : area;
      const did = `diff_${label.replace(/\s+/g, "_").toLowerCase()}`;
      ensureNode(did, label, "difficulty", "high", nodes, nodeIds);
    }

    // Prerequisite chain links
    for (const [from, to] of skeleton.prerequisite_chain || []) {
      const fid = `concept_${from.replace(/\s+/g, "_").toLowerCase()}`;
      const tid = `concept_${to.replace(/\s+/g, "_").toLowerCase()}`;
      ensureNode(fid, from, "concept", "medium", nodes, nodeIds);
      ensureNode(tid, to, "concept", "medium", nodes, nodeIds);
      links.push({ source: fid, target: tid, relation: "prerequisite" });
    }

    return { nodes, links };
  }, [skeleton]);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    const container = svg.parentElement;
    const width = container?.clientWidth || 700;
    const height = 500;

    d3.select(svg).selectAll("*").remove();
    const { nodes, links } = buildGraph();
    if (nodes.length === 0) return;

    const svgEl = d3.select(svg).attr("width", width).attr("height", height);
    const g = svgEl.append("g");

    const zoom = d3.zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.3, 3])
      .on("zoom", (event) => { g.attr("transform", event.transform); });
    svgEl.call(zoom);

    const nodeColor = (d: GraphNode) => {
      if (d.nodeType === "difficulty") return "#ef4444";
      if (d.nodeType === "chapter") return "#111317";
      return "#F59E0B";
    };

    const nodeRadius = (d: GraphNode) => {
      if (d.nodeType === "chapter") return d.importance === "high" ? 22 : d.importance === "medium" ? 16 : 12;
      if (d.nodeType === "difficulty") return 14;
      return d.importance === "high" ? 18 : 12;
    };

    const simulation = d3.forceSimulation<GraphNode>(nodes)
      .force("link", d3.forceLink<GraphNode, GraphLink>(links).id(d => d.id).distance(100))
      .force("charge", d3.forceManyBody().strength(-300))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collision", d3.forceCollide<GraphNode>().radius(d => nodeRadius(d) + 10));

    const link = g.append("g").selectAll<SVGLineElement, GraphLink>("line")
      .data(links).join("line")
      .attr("stroke", "#ccc").attr("stroke-width", 1.5)
      .attr("stroke-dasharray", d => d.relation === "prerequisite" ? "5,3" : "none");

    const node = g.append("g").selectAll<SVGGElement, GraphNode>("g")
      .data(nodes).join("g")
      .attr("cursor", d => d.nodeType === "concept" ? "pointer" : "default")
      .call(d3.drag<SVGGElement, GraphNode>()
        .on("start", (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on("end", (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    node.append("circle")
      .attr("r", d => nodeRadius(d))
      .attr("fill", d => nodeColor(d))
      .attr("stroke", "#fff").attr("stroke-width", 2);

    node.append("text")
      .text(d => d.label.length > 15 ? d.label.slice(0, 15) + "..." : d.label)
      .attr("text-anchor", "middle").attr("dy", d => nodeRadius(d) + 14)
      .attr("font-size", "11px").attr("fill", "#374151");

    node.on("click", (_event, d) => {
      if (d.nodeType === "concept" && onConceptClick) {
        onConceptClick(d.label);
      }
    });

    node.append("title").text(d => `${d.label} [${d.nodeType}]`);

    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as GraphNode).x!)
        .attr("y1", d => (d.source as GraphNode).y!)
        .attr("x2", d => (d.target as GraphNode).x!)
        .attr("y2", d => (d.target as GraphNode).y!);
      node.attr("transform", d => `translate(${d.x},${d.y})`);
    });

    simulation.alpha(1).restart();
    setTimeout(() => simulation.stop(), 8000);

    return () => { simulation.stop(); };
  }, [skeleton, buildGraph, onConceptClick]);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <svg ref={svgRef} className="w-full" style={{ minHeight: 500 }} />
    </div>
  );
}
