"""Evidence-first contracts for the V2 course knowledge system.

``SourceFragment`` is the durable, directly locatable unit of material
evidence.  Everything derived from course material should keep an
``EvidenceRef`` instead of treating a filename or a display locator as an
identifier.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator


SourceFragmentKind = Literal[
    "paragraph",
    "formula",
    "table",
    "figure_context",
    "visual_derived",
]
EvidenceSourceType = Literal[
    "material",
    "source_fragment",
    "semantic_atom",
    "visual_atom",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SourceFragment(BaseModel):
    """A stable, course-scoped and directly locatable source evidence unit.

    ``fragment_id`` is deterministic for a specific course/material/revision/ordinal
    and content hash.  It is deliberately opaque: callers must use the
    explicit scope fields rather than trying to parse identity from the ID.
    """

    fragment_id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)
    material_revision: int = Field(ge=0)
    ordinal: int = Field(ge=0)
    text: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    slide_start: int | None = Field(default=None, ge=1)
    slide_end: int | None = Field(default=None, ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    kind: SourceFragmentKind
    asset_id: str | None = None
    parser_name: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    created_at: str = Field(default_factory=_utc_now)

    @model_validator(mode="after")
    def validate_location_ranges(self) -> "SourceFragment":
        if self.char_end < self.char_start:
            raise ValueError("char_end must be greater than or equal to char_start")
        if (
            self.page_start is not None
            and self.page_end is not None
            and self.page_end < self.page_start
        ):
            raise ValueError("page_end must not precede page_start")
        if (
            self.slide_start is not None
            and self.slide_end is not None
            and self.slide_end < self.slide_start
        ):
            raise ValueError("slide_end must not precede slide_start")
        return self

    def locator(self) -> str:
        """Return a display-only locator; ``fragment_id`` remains the lookup key."""
        parts: list[str] = []
        if self.heading_path:
            parts.append(" > ".join(self.heading_path))
        if self.page_start is not None:
            if self.page_end is None or self.page_end == self.page_start:
                parts.append(f"p.{self.page_start}")
            else:
                parts.append(f"pp.{self.page_start}-{self.page_end}")
        elif self.slide_start is not None:
            if self.slide_end is None or self.slide_end == self.slide_start:
                parts.append(f"slide {self.slide_start}")
            else:
                parts.append(f"slides {self.slide_start}-{self.slide_end}")
        if not parts:
            parts.append(f"fragment {self.ordinal + 1}")
        return "；".join(parts)


class EvidenceRef(BaseModel):
    """The only reference shape that may support a material-based claim.

    ``source_type`` and ``source_id`` identify the immediate source object.
    They default to the material source so the minimal ADR example remains
    convenient, but are always populated after validation.  ``fragment_id``
    is the durable key used to open the source preview.
    """

    course_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)
    fragment_id: str = Field(min_length=1)
    material_revision: int = Field(ge=0)
    locator: str = Field(min_length=1)
    quote: str | None = None
    source_type: EvidenceSourceType = "material"
    source_id: str | None = None

    @model_validator(mode="after")
    def fill_and_validate_source_identity(self) -> "EvidenceRef":
        if self.source_id is None:
            if self.source_type == "material":
                self.source_id = self.material_id
            elif self.source_type == "source_fragment":
                self.source_id = self.fragment_id
            else:
                raise ValueError(
                    f"{self.source_type} EvidenceRef requires an explicit source_id"
                )
        if not self.source_id.strip():
            raise ValueError("EvidenceRef source_id must not be blank")
        if self.source_type == "material" and self.source_id != self.material_id:
            raise ValueError("material EvidenceRef source_id must equal material_id")
        if self.source_type == "source_fragment" and self.source_id != self.fragment_id:
            raise ValueError("source_fragment EvidenceRef source_id must equal fragment_id")
        return self

    @classmethod
    def from_source_fragment(
        cls,
        fragment: SourceFragment,
        *,
        quote: str | None = None,
    ) -> "EvidenceRef":
        """Build a valid material evidence reference from a real fragment."""
        return cls(
            course_id=fragment.course_id,
            material_id=fragment.material_id,
            fragment_id=fragment.fragment_id,
            material_revision=fragment.material_revision,
            locator=fragment.locator(),
            quote=quote,
            source_type="material",
            source_id=fragment.material_id,
        )


class SourceFragmentPreview(BaseModel):
    """Current-revision source text returned when a citation is opened.

    This is intentionally a V2 endpoint contract rather than a variation of
    the legacy ``SourcePreviewResponse``.  Citation payloads use
    :class:`EvidenceRef`; opening one returns this flattened, minimal source
    view without promoting internal parser metadata to a public contract.
    """

    course_id: str = Field(min_length=1)
    material_id: str = Field(min_length=1)
    material_revision: int = Field(ge=0)
    fragment_id: str = Field(min_length=1)
    file_name: str = Field(min_length=1)
    text: str = Field(min_length=1)
    locator: str = Field(min_length=1)
    heading_path: list[str] = Field(default_factory=list)
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    slide_start: int | None = Field(default=None, ge=1)
    slide_end: int | None = Field(default=None, ge=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    kind: SourceFragmentKind
