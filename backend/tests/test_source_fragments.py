"""V2 source evidence contracts, deterministic builder, and SQLite scope tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import EvidenceRef
from app.schemas.foxsay import Course, Material
from app.services.source_fragments import build_source_fragments


LINEAR_ALGEBRA_MARKDOWN = """<!-- PAGE_START 1 -->
# 第一章 向量空间
## 1.1 定义
向量空间是对加法和数乘封闭的集合。

$$
A x = b
$$
\\tag{Formula_1}

| 条件 | 含义 |
| --- | --- |
| 封闭 | 运算结果仍在空间内 |

<!-- PAGE_END 1 -->
<!-- PAGE_START 2 -->
## 1.2 特征值
![特征向量示意图](assets/eigenvector.png)

若 $A v = \\lambda v$，则 $\\lambda$ 是特征值。
<!-- PAGE_END 2 -->
"""


@pytest.fixture
def store(tmp_path: Path):
    database = SqliteStore(tmp_path / "source-fragments.db")
    database.create_course(Course(id="course-a", title="线性代数 A", status="empty"))
    database.create_course(Course(id="course-b", title="线性代数 B", status="empty"))
    database.create_material(
        Material(
            id="material-a",
            course_id="course-a",
            filename="linear-algebra.md",
            kind="text_note",
            status="processing",
        )
    )
    database.create_material(
        Material(
            id="material-b",
            course_id="course-b",
            filename="linear-algebra.md",
            kind="text_note",
            status="processing",
        )
    )
    yield database
    database.close()


def _build(
    *,
    course_id: str = "course-a",
    material_id: str = "material-a",
    material_revision: int = 7,
    markdown: str = LINEAR_ALGEBRA_MARKDOWN,
):
    return build_source_fragments(
        markdown,
        course_id=course_id,
        material_id=material_id,
        material_revision=material_revision,
        parser_name="synthetic-linear-algebra-parser",
    )


def test_builder_preserves_heading_path_page_ranges_and_protected_blocks():
    fragments = _build()

    assert [fragment.kind for fragment in fragments] == [
        "paragraph",
        "formula",
        "table",
        "figure_context",
        "paragraph",
    ]
    assert fragments[0].heading_path == ["第一章 向量空间", "1.1 定义"]
    assert (fragments[0].page_start, fragments[0].page_end) == (1, 1)
    assert fragments[1].text == "$$\nA x = b\n$$\n\\tag{Formula_1}"
    assert fragments[2].text == (
        "| 条件 | 含义 |\n| --- | --- |\n| 封闭 | 运算结果仍在空间内 |"
    )
    assert fragments[3].heading_path == ["第一章 向量空间", "1.2 特征值"]
    assert fragments[3].kind == "figure_context"
    assert (fragments[3].page_start, fragments[3].page_end) == (2, 2)
    assert fragments[4].text == "若 $A v = \\lambda v$，则 $\\lambda$ 是特征值。"

    for fragment in fragments:
        assert (
            LINEAR_ALGEBRA_MARKDOWN[fragment.char_start : fragment.char_end]
            == fragment.text
        )


def test_builder_fragment_ids_are_stable_and_scope_revision_sensitive():
    first = _build()
    same_input = _build()
    another_course = _build(course_id="course-b", material_id="material-b")
    next_revision = _build(material_revision=8)

    assert [fragment.fragment_id for fragment in first] == [
        fragment.fragment_id for fragment in same_input
    ]
    assert [fragment.fragment_id for fragment in first] != [
        fragment.fragment_id for fragment in another_course
    ]
    assert [fragment.fragment_id for fragment in first] != [
        fragment.fragment_id for fragment in next_revision
    ]
    assert [fragment.ordinal for fragment in first] == list(range(len(first)))


def test_evidence_ref_uses_real_fragment_identity_and_requires_derived_source_id():
    fragment = _build()[0]
    reference = EvidenceRef.from_source_fragment(fragment, quote=fragment.text[:8])

    assert reference.course_id == "course-a"
    assert reference.fragment_id == fragment.fragment_id
    assert reference.source_type == "material"
    assert reference.source_id == "material-a"
    assert reference.locator == "第一章 向量空间 > 1.1 定义；p.1"

    with pytest.raises(ValidationError, match="requires an explicit source_id"):
        EvidenceRef(
            course_id="course-a",
            material_id="material-a",
            fragment_id=fragment.fragment_id,
            material_revision=7,
            locator="p.1",
            source_type="semantic_atom",
        )

    derived_reference = EvidenceRef(
        course_id="course-a",
        material_id="material-a",
        fragment_id=fragment.fragment_id,
        material_revision=7,
        locator="p.1",
        source_type="semantic_atom",
        source_id="atom-real-id",
    )
    assert derived_reference.source_id == "atom-real-id"


def test_replace_source_fragments_is_idempotent_and_removes_stale_rows(store: SqliteStore):
    first_build = _build()
    first_write = store.replace_source_fragments(
        "course-a", "material-a", 7, first_build
    )
    first_created_at = {fragment.fragment_id: fragment.created_at for fragment in first_write}

    second_build = _build()
    second_write = store.replace_source_fragments(
        "course-a", "material-a", 7, second_build
    )

    assert [fragment.fragment_id for fragment in first_write] == [
        fragment.fragment_id for fragment in second_write
    ]
    assert {fragment.fragment_id: fragment.created_at for fragment in second_write} == first_created_at
    assert len(store.list_source_fragments("course-a", material_id="material-a", material_revision=7)) == len(
        first_build
    )

    changed_markdown = LINEAR_ALGEBRA_MARKDOWN.replace(
        "向量空间是对加法和数乘封闭的集合。",
        "向量空间还要求包含零向量。",
    )
    replacement = _build(markdown=changed_markdown)
    replaced = store.replace_source_fragments("course-a", "material-a", 7, replacement)

    assert {fragment.fragment_id for fragment in replaced} == {
        fragment.fragment_id for fragment in replacement
    }
    old_first_fragment = first_build[0]
    assert store.get_source_fragment("course-a", old_first_fragment.fragment_id) is None


def test_source_fragment_store_never_reads_or_writes_across_courses(store: SqliteStore):
    fragments = _build()
    store.replace_source_fragments("course-a", "material-a", 7, fragments)

    assert store.get_source_fragment("course-b", fragments[0].fragment_id) is None
    assert store.list_source_fragments("course-b") == []
    assert (
        store.get_source_fragment(
            "course-a",
            fragments[0].fragment_id,
            material_id="material-b",
        )
        is None
    )

    with pytest.raises(ValueError, match="must match the requested"):
        store.replace_source_fragments("course-b", "material-b", 7, fragments)

    with pytest.raises(ValueError, match="does not belong to course"):
        store.replace_source_fragments("course-b", "material-a", 7, [])
