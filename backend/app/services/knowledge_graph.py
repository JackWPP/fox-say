import difflib
import json
from typing import Any

import networkx as nx

from app.schemas.foxsay import CourseSkeleton, CourseSkeletonChapter


class KnowledgeGraph:
    _instances: dict[str, "KnowledgeGraph"] = {}

    def __init__(self, course_id: str) -> None:
        self.course_id = course_id
        self._graph = nx.DiGraph()
        self._dirty = False

    @classmethod
    def for_course(cls, course_id: str, store: Any = None) -> "KnowledgeGraph":
        if course_id not in cls._instances:
            instance = cls(course_id)
            if store is not None:
                instance._load_from_store(store)
            cls._instances[course_id] = instance
        return cls._instances[course_id]

    def _load_from_store(self, store: Any) -> None:
        data_json = store.load_knowledge_graph(self.course_id)
        if data_json:
            data = json.loads(data_json)
            for node in data.get("nodes", []):
                self._graph.add_node(node["id"], **node.get("attrs", {}))
            for edge in data.get("edges", []):
                self._graph.add_edge(edge["from"], edge["to"], **edge.get("attrs", {}))

    def save(self, store: Any) -> None:
        nodes = [{"id": n, "attrs": dict(self._graph.nodes[n])} for n in self._graph.nodes]
        edges = [{"from": u, "to": v, "attrs": dict(self._graph.edges[u, v])} for u, v in self._graph.edges]
        data_json = json.dumps({"nodes": nodes, "edges": edges}, ensure_ascii=False)
        store.save_knowledge_graph(self.course_id, data_json)
        self._dirty = False

    def add_concept(self, concept_id: str, label: str, metadata: dict[str, Any] | None = None) -> None:
        self._graph.add_node(concept_id, label=label, **(metadata or {}))
        self._dirty = True

    def add_dependency(self, from_concept: str, to_concept: str, relation_type: str = "prerequisite") -> None:
        self._graph.add_edge(from_concept, to_concept, relation_type=relation_type)
        self._dirty = True

    def merge_triples(self, triples: list[dict]) -> int:
        added = 0
        for t in triples:
            subject_id = t["subject"].replace(" ", "_").lower()
            object_id = t["object"].replace(" ", "_").lower()
            relation = t.get("relation", "relates_to")

            if subject_id not in self._graph.nodes:
                self._graph.add_node(
                    subject_id,
                    label=t["subject"],
                    material_id=t.get("material_id", ""),
                    chunk_index=t.get("chunk_index", -1),
                    source_text=t.get("source_text", ""),
                    file_name=t.get("file_name", ""),
                )
                added += 1

            if object_id not in self._graph.nodes:
                self._graph.add_node(
                    object_id,
                    label=t["object"],
                    material_id=t.get("material_id", ""),
                    chunk_index=t.get("chunk_index", -1),
                    source_text=t.get("source_text", ""),
                    file_name=t.get("file_name", ""),
                )
                added += 1

            if not self._graph.has_edge(subject_id, object_id):
                self._graph.add_edge(subject_id, object_id, relation_type=relation)
                added += 1

        if added > 0:
            self._dirty = True
        return added

    def get_prerequisite_chain(self) -> list[tuple[str, str]]:
        return list(self._graph.edges())

    def get_difficulty_areas(self) -> list[str]:
        in_degrees = dict(self._graph.in_degree())
        sorted_nodes = sorted(in_degrees, key=lambda n: in_degrees[n], reverse=True)
        return [n for n in sorted_nodes if in_degrees[n] > 0]

    def get_concept_count(self) -> int:
        return self._graph.number_of_nodes()

    def get_neighbors(self, concept_id: str, depth: int = 1) -> dict:
        if concept_id not in self._graph.nodes:
            return {"nodes": [], "edges": []}
        sub = nx.ego_graph(self._graph, concept_id, radius=depth)
        return {
            "nodes": [{"id": n, "label": self._graph.nodes[n].get("label", n)} for n in sub.nodes],
            "edges": [
                {"from": u, "to": v, "relation": self._graph.edges[u, v].get("relation_type", "")}
                for u, v in sub.edges
            ],
        }

    def get_path(self, from_concept: str, to_concept: str) -> list[str] | None:
        try:
            return nx.shortest_path(self._graph, from_concept, to_concept)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_subgraph(self, concept_ids: list[str]) -> dict:
        existing = [n for n in concept_ids if n in self._graph.nodes]
        if not existing:
            return {"nodes": [], "edges": []}
        sub = self._graph.subgraph(existing)
        return {
            "nodes": [{"id": n, "label": self._graph.nodes[n].get("label", n)} for n in sub.nodes],
            "edges": [
                {"from": u, "to": v, "relation": self._graph.edges[u, v].get("relation_type", "")}
                for u, v in sub.edges
            ],
        }

    def search_concepts(self, query: str) -> list[str]:
        q = query.lower()
        results: list[str] = []
        for node_id in self._graph.nodes:
            label = str(self._graph.nodes[node_id].get("label", node_id)).lower()
            if q in label:
                results.append(node_id)
        return results

    def search_concepts_fuzzy(self, query: str, threshold: float = 0.6) -> list[dict]:
        """Fuzzy search concepts by label. Falls back to difflib for inexact matches.
        Returns list of {id, label, match_type: 'exact'|'fuzzy'}."""
        q = query.lower()
        results: list[dict] = []

        # Exact/substring match first
        matched_ids: set[str] = set()
        for node_id in self._graph.nodes:
            label = str(self._graph.nodes[node_id].get("label", node_id))
            if q in label.lower():
                results.append({"id": node_id, "label": label, "match_type": "exact"})
                matched_ids.add(node_id)

        # Fuzzy fallback for unmatched
        if not results:
            all_labels = {
                node_id: str(self._graph.nodes[node_id].get("label", node_id))
                for node_id in self._graph.nodes
            }
            candidates = list(all_labels.values())
            close = difflib.get_close_matches(q, candidates, n=5, cutoff=threshold)
            for label in close:
                for node_id, lbl in all_labels.items():
                    if lbl == label and node_id not in matched_ids:
                        results.append({"id": node_id, "label": label, "match_type": "fuzzy"})
                        matched_ids.add(node_id)

        return results

    def to_context(self, node_ids: list[str] | None = None) -> str:
        if node_ids:
            sub = self.get_subgraph(node_ids)
            edges = sub["edges"]
            nodes = sub["nodes"]
        else:
            edges = [
                {"from": u, "to": v, "relation": self._graph.edges[u, v].get("relation_type", "")}
                for u, v in self._graph.edges
            ]
            nodes = [
                {"id": n, "label": self._graph.nodes[n].get("label", n)} for n in self._graph.nodes
            ]

        if not edges:
            return ""

        node_labels: dict[str, str] = {n["id"]: n["label"] for n in nodes}
        lines: list[str] = []
        for e in edges:
            subj_label = node_labels.get(e["from"], e["from"])
            obj_label = node_labels.get(e["to"], e["to"])
            rel = e.get("relation", "relates_to")
            # Collect source info from edge or node metadata
            src = self._graph.edges.get((e["from"], e["to"]), {})
            file_name = src.get("file_name", "") or self._graph.nodes.get(e["from"], {}).get("file_name", "")
            chunk_idx = src.get("chunk_index", -1) or self._graph.nodes.get(e["from"], {}).get("chunk_index", -1)
            source = f" (来源: {file_name}, chunk {chunk_idx})" if file_name and chunk_idx >= 0 else ""
            lines.append(f"{subj_label} {rel} {obj_label}{source}")

        return "\n".join(lines)

    def to_skeleton(self, course_id: str, chapters_data: list[dict[str, Any]]) -> CourseSkeleton:
        chapters: list[CourseSkeletonChapter] = []
        for ch in chapters_data:
            chapters.append(CourseSkeletonChapter(
                id=ch["id"],
                title=ch["title"],
                key_concepts=ch.get("key_concepts", []),
                importance=ch.get("importance", "medium"),
                exam_weight=ch.get("exam_weight", 0.0),
            ))

        core_concepts: list[str] = []
        for node in self._graph.nodes:
            core_concepts.append(self._graph.nodes[node].get("label", node))

        difficulty_areas = self.get_difficulty_areas()
        prerequisite_chain: list[list[str]] = []
        for u, v in self._graph.edges:
            prerequisite_chain.append([u, v])

        return CourseSkeleton(
            course_id=course_id,
            chapters=chapters,
            core_concepts=core_concepts,
            difficulty_areas=difficulty_areas,
            prerequisite_chain=prerequisite_chain,
        )

    @classmethod
    def clear(cls, course_id: str | None = None) -> None:
        if course_id is not None:
            cls._instances.pop(course_id, None)
        else:
            cls._instances.clear()
