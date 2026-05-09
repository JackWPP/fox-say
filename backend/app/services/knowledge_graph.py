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

    def get_prerequisite_chain(self) -> list[tuple[str, str]]:
        return list(self._graph.edges())

    def get_difficulty_areas(self) -> list[str]:
        in_degrees = dict(self._graph.in_degree())
        sorted_nodes = sorted(in_degrees, key=lambda n: in_degrees[n], reverse=True)
        return [n for n in sorted_nodes if in_degrees[n] > 0]

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
