"""EvidencePack: the bounded evidence prepared for one writer call."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.retrieval_answer import RetrievalHit, RetrievalOutcome


class EvidencePack(BaseModel):
    """What the writer model receives as grounding context.

    ``selected_hits`` is the bounded, score-ordered subset of the
    ``RetrievalOutcome``'s hits that the service chose for the writer prompt.
    ``context_text`` is the compact rendering of those hits (canonical text +
    locator) that is actually placed in the prompt.  ``allowed_fragment_ids``
    is the opaque set the model may choose from for citation; the server
    assembler rejects anything outside this set.
    """

    outcome: RetrievalOutcome
    selected_hits: list[RetrievalHit] = Field(default_factory=list)
    context_text: str = ""
    allowed_fragment_ids: list[str] = Field(default_factory=list)
