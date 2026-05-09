from typing import Any


class CourseStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def create(self, course_id: str, course: Any) -> Any:
        self._data[course_id] = course
        return course

    def get(self, course_id: str) -> Any | None:
        return self._data.get(course_id)

    def get_all(self) -> list[Any]:
        return list(self._data.values())

    def update(self, course_id: str, course: Any) -> Any | None:
        if course_id not in self._data:
            return None
        self._data[course_id] = course
        return course


class MaterialStore:
    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    def _ensure_course(self, course_id: str) -> None:
        if course_id not in self._data:
            self._data[course_id] = {}

    def create(self, course_id: str, material_id: str, material: Any) -> Any:
        self._ensure_course(course_id)
        self._data[course_id][material_id] = material
        return material

    def get(self, course_id: str, material_id: str) -> Any | None:
        return self._data.get(course_id, {}).get(material_id)

    def get_all(self, course_id: str) -> list[Any]:
        return list(self._data.get(course_id, {}).values())

    def update(self, course_id: str, material_id: str, material: Any) -> Any | None:
        if course_id not in self._data or material_id not in self._data[course_id]:
            return None
        self._data[course_id][material_id] = material
        return material


class SkeletonStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def create(self, course_id: str, skeleton: Any) -> Any:
        self._data[course_id] = skeleton
        return skeleton

    def get(self, course_id: str) -> Any | None:
        return self._data.get(course_id)

    def get_all(self) -> list[Any]:
        return list(self._data.values())

    def update(self, course_id: str, skeleton: Any) -> Any | None:
        if course_id not in self._data:
            return None
        self._data[course_id] = skeleton
        return skeleton


class ReviewPlanStore:
    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def create(self, course_id: str, plan: Any) -> Any:
        self._data[course_id] = plan
        return plan

    def get(self, course_id: str) -> Any | None:
        return self._data.get(course_id)

    def get_all(self) -> list[Any]:
        return list(self._data.values())

    def update(self, course_id: str, plan: Any) -> Any | None:
        if course_id not in self._data:
            return None
        self._data[course_id] = plan
        return plan
