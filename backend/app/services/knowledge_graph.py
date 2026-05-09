from typing import Any

import networkx as nx

from app.schemas.foxsay import CourseSkeleton, CourseSkeletonChapter


class KnowledgeGraph:
    _instances: dict[str, "KnowledgeGraph"] = {}

    def __init__(self, course_id: str) -> None:
        self.course_id = course_id
        self._graph = nx.DiGraph()

    @classmethod
    def for_course(cls, course_id: str) -> "KnowledgeGraph":
        if course_id not in cls._instances:
            cls._instances[course_id] = cls(course_id)
        return cls._instances[course_id]

    def add_concept(self, concept_id: str, label: str, metadata: dict[str, Any] | None = None) -> None:
        self._graph.add_node(concept_id, label=label, **(metadata or {}))

    def add_dependency(self, from_concept: str, to_concept: str, relation_type: str = "prerequisite") -> None:
        self._graph.add_edge(from_concept, to_concept, relation_type=relation_type)

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
