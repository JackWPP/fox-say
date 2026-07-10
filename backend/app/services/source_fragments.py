"""Deterministic construction of V2 material evidence fragments.

This module intentionally consumes already-normalized Markdown only.  It does
not parse files, call models, write vectors, or decide material revisions.
That keeps fragment identity reproducible for a worker retry.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from app.schemas.evidence import SourceFragment, SourceFragmentKind


_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*#*\s*$")
_PAGE_START_RE = re.compile(r"^\s*<!--\s*PAGE_START\s+(\d+)\s*-->\s*$", re.IGNORECASE)
_PAGE_END_RE = re.compile(r"^\s*<!--\s*PAGE_END\s+(\d+)\s*-->\s*$", re.IGNORECASE)
_HTML_TABLE_START_RE = re.compile(r"^\s*<table(?:\s|>)", re.IGNORECASE)
_HTML_TABLE_END_RE = re.compile(r"</table\s*>", re.IGNORECASE)
_FENCE_RE = re.compile(r"^\s*(`{3,}|~{3,})")
_BEGIN_EQUATION_RE = re.compile(r"^\s*\\begin\{([A-Za-z*]+)\}\s*$")
_FIGURE_LABEL_RE = re.compile(r"^\s*\[(?:image|figure)_\d+\]\s*$", re.IGNORECASE)


@dataclass(frozen=True)
class _MarkdownLine:
    """A Markdown line with offsets in the original normalized document."""

    content: str
    start: int
    end: int


def build_source_fragments(
    markdown: str,
    *,
    course_id: str,
    material_id: str,
    material_revision: int,
    parser_name: str,
    max_paragraph_chars: int | None = None,
) -> list[SourceFragment]:
    """Build deterministic, source-safe fragments from normalized Markdown.

    Args:
        markdown: Markdown after FoxSay normalization.  Page anchors use
            ``<!-- PAGE_START n -->`` / ``<!-- PAGE_END n -->``.
        course_id: Explicit course scope to embed in every fragment identity.
        material_id: Explicit source material scope.
        material_revision: Immutable integer revision for this material input.
        parser_name: Parser that produced the normalized Markdown.
        max_paragraph_chars: Optional further split limit for normal prose.
            It never applies to formulas, tables, figures, or fenced code.

    Returns:
        Fragments in source order.  IDs are stable for identical input scope,
        revision, ordinal and content; timestamps are intentionally not part
        of the ID.

    Raises:
        ValueError: For invalid scope/input or an unterminated protected block.
    """
    if not markdown or not markdown.strip():
        raise ValueError("normalized Markdown must not be empty")
    if not course_id.strip():
        raise ValueError("course_id is required")
    if not material_id.strip():
        raise ValueError("material_id is required")
    if material_revision < 0:
        raise ValueError("material_revision must be non-negative")
    if not parser_name.strip():
        raise ValueError("parser_name is required")
    if max_paragraph_chars is not None and max_paragraph_chars <= 0:
        raise ValueError("max_paragraph_chars must be positive when provided")

    lines = _split_lines(markdown)
    fragments: list[SourceFragment] = []
    heading_path: list[str] = []
    paragraph_lines: list[_MarkdownLine] = []
    active_page_start: int | None = None
    page_fragment_start: int | None = None

    def emit_span(
        kind: SourceFragmentKind,
        start: int,
        end: int,
        *,
        allow_paragraph_split: bool = False,
    ) -> None:
        spans = [(start, end)]
        if kind == "paragraph" and allow_paragraph_split and max_paragraph_chars is not None:
            spans = _split_long_paragraph(markdown, start, end, max_paragraph_chars)

        for span_start, span_end in spans:
            char_start, char_end = _trim_span(markdown, span_start, span_end)
            if char_start == char_end:
                continue
            text = markdown[char_start:char_end]
            content_hash = _sha256(text)
            ordinal = len(fragments)
            fragment_id = _fragment_id(
                course_id=course_id,
                material_id=material_id,
                material_revision=material_revision,
                ordinal=ordinal,
                content_hash=content_hash,
            )
            fragments.append(
                SourceFragment(
                    fragment_id=fragment_id,
                    course_id=course_id,
                    material_id=material_id,
                    material_revision=material_revision,
                    ordinal=ordinal,
                    text=text,
                    heading_path=list(heading_path),
                    page_start=active_page_start,
                    page_end=active_page_start,
                    char_start=char_start,
                    char_end=char_end,
                    kind=kind,
                    parser_name=parser_name,
                    content_hash=content_hash,
                )
            )

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            emit_span(
                "paragraph",
                paragraph_lines[0].start,
                paragraph_lines[-1].end,
                allow_paragraph_split=True,
            )
        paragraph_lines = []

    def close_active_page(page_end: int) -> None:
        nonlocal page_fragment_start
        if page_fragment_start is None:
            return
        for index in range(page_fragment_start, len(fragments)):
            fragment = fragments[index]
            if fragment.page_start is not None and page_end >= fragment.page_start:
                fragments[index] = fragment.model_copy(update={"page_end": page_end})
        page_fragment_start = None

    line_index = 0
    while line_index < len(lines):
        line = lines[line_index]
        stripped = line.content.strip()

        page_start_match = _PAGE_START_RE.match(line.content)
        if page_start_match:
            flush_paragraph()
            if active_page_start is not None:
                close_active_page(active_page_start)
            active_page_start = int(page_start_match.group(1))
            page_fragment_start = len(fragments)
            line_index += 1
            continue

        page_end_match = _PAGE_END_RE.match(line.content)
        if page_end_match:
            flush_paragraph()
            if active_page_start is not None:
                close_active_page(int(page_end_match.group(1)))
            active_page_start = None
            line_index += 1
            continue

        heading_match = _HEADING_RE.match(line.content)
        if heading_match:
            flush_paragraph()
            _update_heading_path(
                heading_path,
                level=len(heading_match.group(1)),
                title=heading_match.group(2).strip(),
            )
            line_index += 1
            continue

        if _is_formula_start(stripped):
            flush_paragraph()
            end_index = _consume_formula(lines, line_index)
            emit_span("formula", line.start, lines[end_index - 1].end)
            line_index = end_index
            continue

        if _HTML_TABLE_START_RE.match(line.content):
            flush_paragraph()
            end_index = _consume_html_table(lines, line_index)
            emit_span("table", line.start, lines[end_index - 1].end)
            line_index = end_index
            continue

        if _is_gfm_table_start(lines, line_index):
            flush_paragraph()
            end_index = _consume_gfm_table(lines, line_index)
            emit_span("table", line.start, lines[end_index - 1].end)
            line_index = end_index
            continue

        fence_match = _FENCE_RE.match(line.content)
        if fence_match:
            flush_paragraph()
            end_index = _consume_fenced_block(lines, line_index, fence_match.group(1))
            emit_span(
                "paragraph",
                line.start,
                lines[end_index - 1].end,
                allow_paragraph_split=False,
            )
            line_index = end_index
            continue

        if _is_figure_context_line(stripped):
            flush_paragraph()
            emit_span("figure_context", line.start, line.end)
            line_index += 1
            continue

        if not stripped:
            flush_paragraph()
            line_index += 1
            continue

        paragraph_lines.append(line)
        line_index += 1

    flush_paragraph()
    if active_page_start is not None:
        close_active_page(active_page_start)
    return fragments


def _split_lines(markdown: str) -> list[_MarkdownLine]:
    lines: list[_MarkdownLine] = []
    cursor = 0
    for raw_line in markdown.splitlines(keepends=True):
        content = raw_line.rstrip("\r\n")
        lines.append(_MarkdownLine(content=content, start=cursor, end=cursor + len(content)))
        cursor += len(raw_line)
    if not lines and markdown:
        lines.append(_MarkdownLine(content=markdown, start=0, end=len(markdown)))
    return lines


def _update_heading_path(path: list[str], *, level: int, title: str) -> None:
    del path[level - 1 :]
    path.append(title)


def _is_formula_start(stripped_line: str) -> bool:
    return (
        stripped_line.startswith("$$")
        or stripped_line == r"\["
        or _BEGIN_EQUATION_RE.match(stripped_line) is not None
    )


def _consume_formula(lines: list[_MarkdownLine], start_index: int) -> int:
    """Return the exclusive line index of one complete block formula."""
    opening = lines[start_index].content.strip()
    if opening.startswith("$$"):
        if opening.count("$$") >= 2:
            end_index = start_index + 1
        else:
            end_index = _find_line_containing(lines, start_index + 1, "$$")
    elif opening == r"\[":
        end_index = _find_line_containing(lines, start_index + 1, r"\]")
    else:
        match = _BEGIN_EQUATION_RE.match(opening)
        if match is None:  # pragma: no cover - guarded by _is_formula_start
            raise ValueError("formula block start could not be interpreted")
        end_marker = rf"\end{{{match.group(1)}}}"
        end_index = _find_line_containing(lines, start_index + 1, end_marker)

    if end_index < len(lines) and lines[end_index].content.strip().startswith(r"\tag{"):
        end_index += 1
    return end_index


def _find_line_containing(
    lines: list[_MarkdownLine], start_index: int, marker: str
) -> int:
    for index in range(start_index, len(lines)):
        if marker in lines[index].content:
            return index + 1
    raise ValueError(f"unterminated protected Markdown block (missing {marker!r})")


def _consume_html_table(lines: list[_MarkdownLine], start_index: int) -> int:
    for index in range(start_index, len(lines)):
        if _HTML_TABLE_END_RE.search(lines[index].content):
            return index + 1
    raise ValueError("unterminated HTML table in normalized Markdown")


def _is_gfm_table_start(lines: list[_MarkdownLine], index: int) -> bool:
    if index + 1 >= len(lines):
        return False
    header = lines[index].content.strip()
    separator = lines[index + 1].content.strip()
    return "|" in header and _is_gfm_separator(separator)


def _is_gfm_separator(line: str) -> bool:
    trimmed = line.strip().strip("|")
    cells = [cell.strip() for cell in trimmed.split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _consume_gfm_table(lines: list[_MarkdownLine], start_index: int) -> int:
    index = start_index + 2
    while index < len(lines):
        stripped = lines[index].content.strip()
        if not stripped or "|" not in stripped:
            break
        index += 1
    return index


def _consume_fenced_block(
    lines: list[_MarkdownLine], start_index: int, opening_fence: str
) -> int:
    marker = opening_fence[0] * len(opening_fence)
    for index in range(start_index + 1, len(lines)):
        if lines[index].content.lstrip().startswith(marker):
            return index + 1
    raise ValueError("unterminated fenced code block in normalized Markdown")


def _is_figure_context_line(stripped_line: str) -> bool:
    return (
        stripped_line.startswith("![")
        or stripped_line.lower().startswith("<img")
        or _FIGURE_LABEL_RE.match(stripped_line) is not None
    )


def _split_long_paragraph(
    markdown: str, start: int, end: int, max_chars: int
) -> list[tuple[int, int]]:
    """Optionally split prose at a deterministic natural boundary.

    Block formula/table/code callers never reach this function.  Inline math
    remains intact by keeping a paragraph that contains a dollar sign whole.
    """
    start, end = _trim_span(markdown, start, end)
    if end - start <= max_chars or "$" in markdown[start:end]:
        return [(start, end)]

    spans: list[tuple[int, int]] = []
    cursor = start
    while end - cursor > max_chars:
        target = cursor + max_chars
        split_at = _best_split_position(markdown, cursor, target)
        if split_at is None:
            split_at = _best_whitespace_position(markdown, cursor, target)
        if split_at is None or split_at <= cursor:
            split_at = target
        part_start, part_end = _trim_span(markdown, cursor, split_at)
        if part_start < part_end:
            spans.append((part_start, part_end))
        cursor = split_at
        while cursor < end and markdown[cursor].isspace():
            cursor += 1

    part_start, part_end = _trim_span(markdown, cursor, end)
    if part_start < part_end:
        spans.append((part_start, part_end))
    return spans


def _best_split_position(markdown: str, start: int, target: int) -> int | None:
    lower_bound = start + max(1, (target - start) // 2)
    for index in range(target - 1, lower_bound - 1, -1):
        if markdown[index] in "\n。！？!?；;":
            return index + 1
    return None


def _best_whitespace_position(markdown: str, start: int, target: int) -> int | None:
    lower_bound = start + max(1, (target - start) // 2)
    for index in range(target - 1, lower_bound - 1, -1):
        if markdown[index].isspace():
            return index + 1
    return None


def _trim_span(markdown: str, start: int, end: int) -> tuple[int, int]:
    while start < end and markdown[start].isspace():
        start += 1
    while end > start and markdown[end - 1].isspace():
        end -= 1
    return start, end


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _fragment_id(
    *,
    course_id: str,
    material_id: str,
    material_revision: int,
    ordinal: int,
    content_hash: str,
) -> str:
    identity = "\x1f".join(
        (course_id, material_id, str(material_revision), str(ordinal), content_hash)
    )
    return f"sf_{_sha256(identity)}"
