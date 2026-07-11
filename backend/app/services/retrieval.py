import json
import math
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.db.sqlite_store import SqliteStore
from app.schemas.evidence import EvidenceRef, SourceFragment
from app.schemas.retrieval_answer import (
    RetrievalChannel,
    RetrievalError,
    RetrievalHit,
    RetrievalOutcome,
    RetrievalWarning,
)
from app.schemas.foxsay import ConfidenceStatus
from app.schemas.knowledge_status import KnowledgeStatus
from app.services.embedding import embed_text, embed_texts
from app.services.knowledge_status import build_knowledge_status
from app.services.vectorstore import QdrantStore

_qdrant = QdrantStore()

GROUND_THRESHOLD = 0.72
AMBIGUOUS_THRESHOLD = 0.55


# V2 source-fragment retrieval -------------------------------------------------
#
# The legacy functions below deliberately retain their old return shapes while
# V2 is being introduced.  This boundary is intentionally self-contained: it
# treats Qdrant as an untrusted candidate index and only emits evidence that
# has been read back through the current-ready SQLite boundary.

_V2_CHANNEL_ORDER: tuple[RetrievalChannel, ...] = (
    "exact",
    "vector",
    "heading_neighborhood",
)
_V2_HEADING_PREFIX = re.compile(
    r"""
    ^\s*(?:
        第\s*(?:\d+|[零〇一二三四五六七八九十百千万两]+)\s*(?:章|节|篇|部分)
        |\d+(?:\s*\.\s*\d+)*(?:\s*(?:章|节))?
        |(?:chapter|section)\s+\d+(?:\s*\.\s*\d+)*
    )\s*[\-—–:：、.．]?\s*
    """,
    re.IGNORECASE | re.VERBOSE,
)


def retrieve_current_fragments(
    store: SqliteStore,
    course_id: str,
    query: str,
    *,
    limit: int = 5,
    selected_material_ids: Sequence[str] | None = None,
    qdrant_store: QdrantStore | None = None,
    embed_query: Callable[[str], list[float]] | None = None,
    enable_vector: bool = True,
) -> RetrievalOutcome:
    """Retrieve only current, ready V2 source evidence for one course.

    Exact title/original-text matching is deterministic and happens before
    any embedding call.  Vector search is optional enrichment only: every
    vector payload is checked against the canonical SQLite scope and then
    hydrated again by ``fragment_id`` before it can become a ``RetrievalHit``.
    This makes stale, cross-course, malformed, or forged Qdrant payloads
    incapable of producing a citation.

    ``selected_material_ids`` is passed directly to the canonical boundary.
    In particular, an explicit empty list means an empty scope; it can never
    fall back to all course materials.
    """
    if not course_id or not course_id.strip():
        raise ValueError("course_id is required for V2 fragment retrieval")
    if limit <= 0:
        raise ValueError("limit must be greater than zero")

    try:
        course = store.get_course(course_id)
        if course is None:
            return _v2_error_outcome(
                course_id,
                source_revision=None,
                knowledge_revision=None,
                error_code="course_not_found",
                error_detail="The requested course does not exist.",
                retriable=False,
            )
        status = build_knowledge_status(store, course_id)
        selected_scope = list(selected_material_ids) if selected_material_ids is not None else None
        canonical_fragments = store.list_current_ready_source_fragments(
            course_id,
            material_ids=selected_scope,
        )
    except Exception as exc:
        return _v2_error_outcome(
            course_id,
            source_revision=None,
            knowledge_revision=None,
            error_code="source_evidence_lookup_failed",
            error_detail=f"Could not load current course evidence: {_v2_exception_detail(exc)}",
            retriable=True,
        )

    source_revision = status.source_revision
    knowledge_revision = status.knowledge_revision
    source_status = status.source_status
    if not canonical_fragments:
        no_evidence = _v2_no_ready_evidence_outcome(
            course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            source_status=source_status,
            material_states=status.materials,
            selected_material_ids=selected_material_ids,
        )
        if no_evidence is not None:
            return no_evidence

    normalized_query = _v2_normalize_exact_text(query)
    if not normalized_query:
        return _v2_error_outcome(
            course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            error_code="invalid_retrieval_query",
            error_detail="A non-empty query is required for source-fragment retrieval.",
            retriable=False,
        )

    canonical_by_id = {fragment.fragment_id: fragment for fragment in canonical_fragments}
    material_scopes = sorted(
        {
            (fragment.material_id, fragment.material_revision)
            for fragment in canonical_fragments
        }
    )
    candidates = _v2_exact_candidates(canonical_fragments, normalized_query)
    warnings: list[RetrievalWarning] = []
    retrieval_failure: RetrievalError | None = None
    course_source_coverage = _v2_course_source_coverage(status)
    if source_status == "partial":
        _v2_add_warning(
            warnings,
            warning_code="partial_source_coverage",
            warning_detail=(
                "Only "
                f"{status.coverage.ready_materials}/{status.coverage.total_materials} "
                "current course materials have ready source evidence."
            ),
        )

    # Hydrate exact hits first.  If they already provide the requested number
    # of grounded evidence units, the grep-like path costs no embedding or
    # vector query at all.  Otherwise semantic candidates may fill gaps.
    exact_primary, exact_hydration_warning = _v2_hydrate_primary_candidates(
        store,
        course_id,
        canonical_by_id=canonical_by_id,
        candidates=candidates,
        limit=limit,
    )
    if exact_hydration_warning is not None:
        _v2_add_warning(
            warnings,
            warning_code="candidate_hydration_dropped",
            warning_detail=exact_hydration_warning,
        )

    exact_relevance = exact_primary[0][2]["score"] if exact_primary else 0.0
    should_query_vector = enable_vector and not (
        exact_primary
        and _v2_confidence_for_score(exact_relevance) == "grounded"
        and len(exact_primary) >= limit
    )

    if should_query_vector:
        query_embedder = embed_query or embed_text
        try:
            embedding = _v2_validate_query_embedding(query_embedder(query))
        except Exception as exc:
            retrieval_failure = RetrievalError(
                error_code="query_embedding_failed",
                error_detail=f"Could not create the retrieval query embedding: {_v2_exception_detail(exc)}",
                retriable=True,
            )
        else:
            try:
                raw_vector_hits = (qdrant_store or _qdrant).search_source_fragments(
                    course_id,
                    embedding,
                    material_scopes,
                    limit=max(limit * 3, 3),
                )
            except Exception as exc:
                retrieval_failure = RetrievalError(
                    error_code="source_fragment_vector_search_failed",
                    error_detail=(
                        "Could not search the current source-fragment vector index: "
                        f"{_v2_exception_detail(exc)}"
                    ),
                    retriable=True,
                )
            else:
                if not isinstance(raw_vector_hits, list):
                    retrieval_failure = RetrievalError(
                        error_code="source_fragment_vector_response_invalid",
                        error_detail="The source-fragment vector index returned an invalid response.",
                        retriable=True,
                    )
                else:
                    vector_candidates, invalid_payload_count = _v2_vector_candidates(
                        raw_vector_hits,
                        course_id=course_id,
                        canonical_by_id=canonical_by_id,
                    )
                    _v2_merge_candidates(candidates, vector_candidates)
                    if invalid_payload_count:
                        _v2_add_warning(
                            warnings,
                            warning_code="invalid_vector_payload_dropped",
                            warning_detail=(
                                f"Dropped {invalid_payload_count} vector candidate(s) that did not "
                                "match current canonical source evidence."
                            ),
                        )
                        if not vector_candidates and not candidates:
                            retrieval_failure = RetrievalError(
                                error_code="source_fragment_vector_payload_invalid",
                                error_detail=(
                                    "The vector index returned candidates, but none matched current "
                                    "course evidence."
                                ),
                                retriable=True,
                            )

    if should_query_vector:
        primary, hydration_warning = _v2_hydrate_primary_candidates(
            store,
            course_id,
            canonical_by_id=canonical_by_id,
            candidates=candidates,
            limit=limit,
        )
        if hydration_warning is not None:
            _v2_add_warning(
                warnings,
                warning_code="candidate_hydration_dropped",
                warning_detail=hydration_warning,
            )
    else:
        primary = exact_primary

    if retrieval_failure is not None:
        if primary:
            _v2_add_warning(
                warnings,
                warning_code=retrieval_failure.error_code,
                warning_detail=retrieval_failure.error_detail,
            )
        else:
            return _v2_error_outcome(
                course_id,
                source_revision=source_revision,
                knowledge_revision=knowledge_revision,
                error_code=retrieval_failure.error_code,
                error_detail=retrieval_failure.error_detail,
                retriable=retrieval_failure.retriable,
                warnings=warnings,
            )

    if candidates and not primary:
        return _v2_error_outcome(
            course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            error_code="canonical_fragment_hydration_failed",
            error_detail=(
                "Retrieval candidates could not be rehydrated as current source evidence."
            ),
            retriable=True,
            warnings=warnings,
        )

    relevance = primary[0][2]["score"] if primary else 0.0
    confidence = _v2_confidence_for_score(relevance)
    if confidence == "out_of_scope":
        # A low-scoring canonical candidate is not evidence for a material
        # answer.  Keeping its score is useful to CRAG, but it must not leak a
        # citation into the transparent supplementary path.
        return RetrievalOutcome(
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            confidence="out_of_scope",
            relevance=relevance,
            coverage=0.0,
            hits=[],
            warnings=warnings,
        )

    primary_hits = [
        _v2_to_hit(fragment, file_name, candidate)
        for fragment, file_name, candidate in primary
    ]
    hits = list(primary_hits)
    if len(hits) < limit:
        hits.extend(
            _v2_heading_neighbors(
                store,
                course_id,
                canonical_fragments=canonical_fragments,
                primary=primary,
                already_selected={hit.evidence.fragment_id for hit in hits},
                limit=limit - len(hits),
                warnings=warnings,
            )
        )

    covered_scopes = {
        (fragment.material_id, fragment.material_revision)
        for fragment, _, _ in primary
    }
    evidence_coverage = len(covered_scopes) / len(material_scopes) if material_scopes else 0.0
    # A query can cover all of its selected ready material scopes while the
    # course as a whole is still partial.  Never promote that situation to
    # 100% coverage: the answer boundary must retain the durable source gap.
    coverage = min(evidence_coverage, course_source_coverage)
    return RetrievalOutcome(
        course_id=course_id,
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        confidence=confidence,
        relevance=relevance,
        coverage=coverage,
        hits=hits,
        warnings=warnings,
    )


def _v2_error_outcome(
    course_id: str,
    *,
    source_revision: str | None,
    knowledge_revision: str | None,
    error_code: str,
    error_detail: str,
    retriable: bool,
    warnings: list[RetrievalWarning] | None = None,
) -> RetrievalOutcome:
    """Build an explicitly failed retrieval result, never a fake no-hit."""
    return RetrievalOutcome(
        course_id=course_id,
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        retrieval_availability="unavailable",
        confidence=None,
        relevance=0.0,
        coverage=0.0,
        hits=[],
        error=RetrievalError(
            error_code=error_code,
            error_detail=error_detail,
            retriable=retriable,
        ),
        warnings=warnings or [],
    )


def _v2_no_ready_evidence_outcome(
    course_id: str,
    *,
    source_revision: str | None,
    knowledge_revision: str | None,
    source_status: str,
    material_states: Sequence[Any],
    selected_material_ids: Sequence[str] | None,
) -> RetrievalOutcome:
    """Separate a truly empty course from unavailable source evidence."""
    if source_status == "empty":
        return RetrievalOutcome(
            course_id=course_id,
            source_revision=source_revision,
            knowledge_revision=knowledge_revision,
            confidence="out_of_scope",
            relevance=0.0,
            coverage=0.0,
            hits=[],
        )

    selected = set(selected_material_ids) if selected_material_ids is not None else None
    relevant_states = [
        item
        for item in material_states
        if selected is None or item.material_id in selected
    ]
    retryable = any(item.status in {"processing", "retryable"} for item in relevant_states)
    if selected_material_ids is None:
        error_code = "source_evidence_unavailable"
        error_detail = "Current course source evidence is not ready for retrieval."
    else:
        error_code = "selected_scope_has_no_ready_evidence"
        error_detail = "The selected materials have no current ready source fragments."
    return _v2_error_outcome(
        course_id,
        source_revision=source_revision,
        knowledge_revision=knowledge_revision,
        error_code=error_code,
        error_detail=error_detail,
        retriable=retryable,
    )


def _v2_course_source_coverage(status: KnowledgeStatus) -> float:
    total = status.coverage.total_materials
    if total <= 0:
        return 0.0
    return max(0.0, min(status.coverage.ready_materials / total, 1.0))


def _v2_normalize_exact_text(value: str) -> str:
    """Normalize Unicode/case and fold whitespace without corrupting formulas."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if not character.isspace())


def _v2_exact_candidates(
    fragments: Sequence[SourceFragment],
    normalized_query: str,
) -> dict[str, dict[str, Any]]:
    """Return direct heading/original-text candidates without embeddings."""
    candidates: dict[str, dict[str, Any]] = {}
    for fragment in fragments:
        heading_score = _v2_heading_exact_score(fragment.heading_path, normalized_query)
        text_score = _v2_text_exact_score(fragment.text, normalized_query)
        score = max(heading_score, text_score)
        if score <= 0:
            continue
        candidates[fragment.fragment_id] = {
            "score": score,
            "channels": {"exact"},
        }
    return candidates


def _v2_heading_exact_score(heading_path: Sequence[str], normalized_query: str) -> float:
    best = 0.0
    for heading in heading_path:
        for normalized_heading in _v2_heading_variants(heading):
            if normalized_heading == normalized_query:
                best = max(best, 1.0)
            elif (
                len(normalized_heading) >= 2
                and len(normalized_query) >= 2
                and (normalized_query in normalized_heading or normalized_heading in normalized_query)
            ):
                # A numbered title phrase embedded in a natural-language
                # question is still deterministic grep-style evidence, not a
                # semantic guess.  The length floor avoids one-character
                # title fragments matching arbitrary prose.
                best = max(best, 0.96)
    return best


def _v2_heading_variants(heading: str) -> tuple[str, ...]:
    """Keep full titles and one deterministic variant without section numbers."""
    full = _v2_normalize_exact_text(heading)
    stripped = _v2_normalize_exact_text(_V2_HEADING_PREFIX.sub("", heading, count=1))
    return tuple(dict.fromkeys(value for value in (full, stripped) if value))


def _v2_text_exact_score(text: str, normalized_query: str) -> float:
    normalized_text = _v2_normalize_exact_text(text)
    if not normalized_text or normalized_query not in normalized_text:
        return 0.0
    return 0.98 if normalized_text == normalized_query else 0.94


def _v2_validate_query_embedding(embedding: list[float]) -> list[float]:
    if not isinstance(embedding, list) or not embedding:
        raise ValueError("the embedding provider returned no query vector")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in embedding
    ):
        raise ValueError("the embedding provider returned an invalid query vector")
    return [float(value) for value in embedding]


def _v2_vector_candidates(
    raw_hits: list[Any],
    *,
    course_id: str,
    canonical_by_id: Mapping[str, SourceFragment],
) -> tuple[dict[str, dict[str, Any]], int]:
    """Validate untrusted vector payloads against current canonical evidence."""
    candidates: dict[str, dict[str, Any]] = {}
    invalid_payload_count = 0
    for raw_hit in raw_hits:
        if not isinstance(raw_hit, Mapping):
            invalid_payload_count += 1
            continue
        payload = raw_hit.get("payload")
        score = _v2_normalize_vector_score(raw_hit.get("score"))
        if not isinstance(payload, Mapping) or score is None:
            invalid_payload_count += 1
            continue

        fragment_id = payload.get("fragment_id")
        if not isinstance(fragment_id, str):
            invalid_payload_count += 1
            continue
        canonical = canonical_by_id.get(fragment_id)
        if canonical is None or not _v2_payload_matches_fragment(payload, canonical, course_id):
            invalid_payload_count += 1
            continue

        candidate = candidates.setdefault(
            fragment_id,
            {"score": score, "channels": {"vector"}},
        )
        candidate["score"] = max(candidate["score"], score)
        candidate["channels"].add("vector")
    return candidates, invalid_payload_count


def _v2_payload_matches_fragment(
    payload: Mapping[str, Any],
    fragment: SourceFragment,
    course_id: str,
) -> bool:
    revision = payload.get("material_revision")
    return (
        payload.get("type") == "source_fragment"
        and payload.get("course_id") == course_id == fragment.course_id
        and payload.get("fragment_id") == fragment.fragment_id
        and payload.get("material_id") == fragment.material_id
        and isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision == fragment.material_revision
        and payload.get("content_hash") == fragment.content_hash
    )


def _v2_normalize_vector_score(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score):
        return None
    return max(0.0, min(score, 1.0))


def _v2_merge_candidates(
    destination: dict[str, dict[str, Any]],
    additions: Mapping[str, Mapping[str, Any]],
) -> None:
    for fragment_id, addition in additions.items():
        candidate = destination.setdefault(
            fragment_id,
            {"score": addition["score"], "channels": set()},
        )
        candidate["score"] = max(candidate["score"], addition["score"])
        candidate["channels"].update(addition["channels"])


def _v2_hydrate_primary_candidates(
    store: SqliteStore,
    course_id: str,
    *,
    canonical_by_id: Mapping[str, SourceFragment],
    candidates: Mapping[str, Mapping[str, Any]],
    limit: int,
) -> tuple[list[tuple[SourceFragment, str, dict[str, Any]]], str | None]:
    """Read candidate IDs back through C1 before making them public hits."""
    hydrated: list[tuple[SourceFragment, str, dict[str, Any]]] = []
    dropped = 0
    for fragment_id, candidate in sorted(
        candidates.items(),
        key=lambda item: (-float(item[1]["score"]), item[0]),
    ):
        expected = canonical_by_id[fragment_id]
        try:
            current = store.get_current_ready_source_fragment_preview(course_id, fragment_id)
        except Exception:
            dropped += 1
            continue
        if current is None:
            dropped += 1
            continue
        fragment, file_name = current
        if not _v2_same_canonical_fragment(fragment, expected):
            dropped += 1
            continue
        hydrated.append((fragment, file_name, dict(candidate)))
        if len(hydrated) == limit:
            break

    warning = None
    if dropped:
        warning = f"Dropped {dropped} candidate(s) that were no longer current canonical evidence."
    return hydrated, warning


def _v2_same_canonical_fragment(left: SourceFragment, right: SourceFragment) -> bool:
    return (
        left.course_id == right.course_id
        and left.material_id == right.material_id
        and left.material_revision == right.material_revision
        and left.fragment_id == right.fragment_id
        and left.content_hash == right.content_hash
    )


def _v2_confidence_for_score(score: float) -> ConfidenceStatus:
    if score >= GROUND_THRESHOLD:
        return "grounded"
    if score >= AMBIGUOUS_THRESHOLD:
        return "ambiguous"
    return "out_of_scope"


def _v2_to_hit(
    fragment: SourceFragment,
    file_name: str,
    candidate: Mapping[str, Any],
) -> RetrievalHit:
    channels: list[RetrievalChannel] = [
        channel
        for channel in _V2_CHANNEL_ORDER
        if channel in candidate["channels"]
    ]
    return RetrievalHit(
        evidence=EvidenceRef.from_source_fragment(fragment),
        file_name=file_name,
        canonical_text=fragment.text,
        score=float(candidate["score"]),
        channels=channels,
    )


def _v2_heading_neighbors(
    store: SqliteStore,
    course_id: str,
    *,
    canonical_fragments: Sequence[SourceFragment],
    primary: Sequence[tuple[SourceFragment, str, Mapping[str, Any]]],
    already_selected: set[str],
    limit: int,
    warnings: list[RetrievalWarning],
) -> list[RetrievalHit]:
    """Add immediate same-heading context without influencing CRAG scores."""
    if limit <= 0:
        return []

    groups: dict[tuple[str, int, tuple[str, ...]], list[SourceFragment]] = {}
    for fragment in canonical_fragments:
        group_key = (fragment.material_id, fragment.material_revision, tuple(fragment.heading_path))
        groups.setdefault(group_key, []).append(fragment)
    for group in groups.values():
        group.sort(key=lambda fragment: (fragment.ordinal, fragment.fragment_id))

    neighbors: list[RetrievalHit] = []
    for primary_fragment, _, anchor_candidate in primary:
        key = (
            primary_fragment.material_id,
            primary_fragment.material_revision,
            tuple(primary_fragment.heading_path),
        )
        group = groups[key]
        by_ordinal = {fragment.ordinal: fragment for fragment in group}
        for neighbor_ordinal in (
            primary_fragment.ordinal - 1,
            primary_fragment.ordinal + 1,
        ):
            neighbor = by_ordinal.get(neighbor_ordinal)
            if neighbor is None:
                continue
            if neighbor.fragment_id in already_selected:
                continue
            try:
                current = store.get_current_ready_source_fragment_preview(
                    course_id,
                    neighbor.fragment_id,
                )
            except Exception:
                current = None
            if current is None:
                _v2_add_warning(
                    warnings,
                    warning_code="heading_neighbor_hydration_dropped",
                    warning_detail=(
                        "A same-heading context fragment was no longer current canonical evidence."
                    ),
                )
                continue
            hydrated, file_name = current
            if not _v2_same_canonical_fragment(hydrated, neighbor):
                _v2_add_warning(
                    warnings,
                    warning_code="heading_neighbor_hydration_dropped",
                    warning_detail=(
                        "A same-heading context fragment no longer matched its canonical identity."
                    ),
                )
                continue
            # The CRAG grade and coverage above are calculated from primary
            # exact/vector evidence only.  Context has a derived score capped
            # below grounded, so even consumers that display it cannot mistake
            # it for an independent match.
            neighbors.append(
                RetrievalHit(
                    evidence=EvidenceRef.from_source_fragment(hydrated),
                    file_name=file_name,
                    canonical_text=hydrated.text,
                    score=min(float(anchor_candidate["score"]) * 0.75, 0.71),
                    channels=["heading_neighborhood"],
                )
            )
            already_selected.add(neighbor.fragment_id)
            if len(neighbors) == limit:
                return neighbors
    return neighbors


def _v2_add_warning(
    warnings: list[RetrievalWarning],
    *,
    warning_code: str,
    warning_detail: str,
) -> None:
    if any(warning.warning_code == warning_code for warning in warnings):
        return
    warnings.append(
        RetrievalWarning(
            warning_code=warning_code,
            warning_detail=warning_detail,
        )
    )


def _v2_exception_detail(exc: Exception) -> str:
    detail = str(exc).strip()
    return detail[:300] if detail else exc.__class__.__name__


def tool_search_materials(course_id: str, query: str, top_k: int = 5) -> str:
    embeddings = embed_texts([query])
    if not embeddings:
        return json.dumps({"results": [], "count": 0, "note": "embedding failed"}, ensure_ascii=False)

    results = _qdrant.search(course_id, embeddings[0], limit=top_k)
    if not results:
        return json.dumps({"results": [], "count": 0, "note": "no matching materials found"}, ensure_ascii=False)

    formatted = []
    for r in results:
        payload = r.get("payload", {})
        is_note = payload.get("type") == "note"
        if is_note:
            file_name = "笔记"
            locator = payload.get("title", "")
            source = f"笔记 · {locator}"
        else:
            file_name = payload.get("file_name", "")
            locator = f"第{payload.get('index', 0) + 1}部分"
            source = f"{file_name} · {locator}"
        formatted.append({
            "score": round(r.get("score", 0), 3),
            "text": payload.get("text", ""),
            "file_name": file_name,
            "locator": locator,
            "source": source,
        })

    return json.dumps({"results": formatted, "count": len(formatted)}, ensure_ascii=False)


def retrieve(
    course_id: str,
    query: str,
    limit: int = 5,
    store: Any = None,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> dict:
    query_embeddings = embed_texts([query])
    if not query_embeddings:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    query_embedding = query_embeddings[0]

    all_results = _search_with_filters(
        course_id, query_embedding, limit=max(limit, 10),
        selected_material_ids=selected_material_ids,
        selected_note_ids=selected_note_ids,
    )

    if not all_results:
        return {"confidence": "out_of_scope", "top_score": 0.0, "results": []}

    top_score = all_results[0]["score"]

    if top_score >= GROUND_THRESHOLD:
        formatted = _format_results("grounded", top_score, all_results[:limit])
    elif top_score >= AMBIGUOUS_THRESHOLD:
        expanded = _search_with_filters(
            course_id, query_embedding, limit=10,
            selected_material_ids=selected_material_ids,
            selected_note_ids=selected_note_ids,
        )
        formatted = _format_results("ambiguous", top_score, expanded)
    else:
        return {"confidence": "out_of_scope", "top_score": top_score, "results": []}

    return formatted


def _search_with_filters(
    course_id: str,
    query_embedding: list[float],
    limit: int = 5,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> list[dict]:
    from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

    all_results: list[dict] = []

    has_material_filter = bool(selected_material_ids)
    has_note_filter = bool(selected_note_ids)

    if not has_material_filter and not has_note_filter:
        return _qdrant.search(course_id, query_embedding, limit=limit)

    if has_material_filter:
        material_filter = Filter(
            must=[
                FieldCondition(key="material_id", match=MatchAny(any=selected_material_ids)),
            ]
        )
        material_results = _qdrant.search(
            course_id, query_embedding, limit=limit, query_filter=material_filter
        )
        all_results.extend(material_results)

    if has_note_filter:
        note_filter = Filter(
            must=[
                FieldCondition(key="type", match=MatchValue(value="note")),
                FieldCondition(key="note_id", match=MatchAny(any=selected_note_ids)),
            ]
        )
        note_results = _qdrant.search(
            course_id, query_embedding, limit=limit, query_filter=note_filter
        )
        all_results.extend(note_results)

    all_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    seen_texts: set[str] = set()
    deduped: list[dict] = []
    for r in all_results:
        text = r.get("payload", {}).get("text", "")
        if text not in seen_texts:
            seen_texts.add(text)
            deduped.append(r)
    return deduped[:limit]


def _format_results(confidence: str, top_score: float, results: list[dict]) -> dict:
    formatted: list[dict] = []
    for r in results:
        payload = r.get("payload", {})
        is_note = payload.get("type") == "note"
        if is_note:
            file_name = "笔记"
            locator = payload.get("title", "")
        else:
            file_name = payload.get("file_name", "")
            locator = payload.get("locator", f"第{payload.get('index', 0) + 1}部分")
        formatted.append({
            "text": payload.get("text", ""),
            "score": r["score"],
            "metadata": {
                "file_name": file_name,
                "locator": locator,
                "is_note": is_note,
                "note_id": payload.get("note_id", ""),
            },
        })
    return {"confidence": confidence, "top_score": top_score, "results": formatted}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _text_overlap_score(query: str, text: str) -> float:
    """Return lowercase character-set Jaccard similarity for legacy fallback."""
    if not query or not text:
        return 0.0
    query_characters = set(query.lower())
    text_characters = set(text.lower())
    if not query_characters or not text_characters:
        return 0.0
    union = query_characters | text_characters
    return len(query_characters & text_characters) / len(union) if union else 0.0


# 章节 embedding 缓存（避免每次查询都重新 embed 所有章节）
_chapter_embedding_cache: dict[str, list[float]] = {}


def _get_chapter_embedding(text: str) -> list[float] | None:
    """获取文本的 embedding，带内存缓存。"""
    cache_key = text[:200]
    if cache_key in _chapter_embedding_cache:
        return _chapter_embedding_cache[cache_key]
    try:
        embs = embed_texts([text])
        if embs:
            _chapter_embedding_cache[cache_key] = embs[0]
            return embs[0]
    except Exception:
        pass
    return None


def search_wiki_layer(
    course_id: str,
    query: str,
    layer: str = "all",
    top_k: int = 5,
    store: Any = None,
    selected_material_ids: list[str] | None = None,
    selected_note_ids: list[str] | None = None,
) -> list[dict]:
    """Cascading Wiki retrieval: chapters → KC (chapter-boosted) → notes.

    Cascade order:
      1. Score ChapterWikis by text overlap → identify top-2 relevant chapters
      2. Score KCs: chapter-matched KCs get a 0.15 boost; all KCs scored by cosine
      3. Notes searched via Qdrant (type=note filter)
    Raw chunks are no longer stored in Qdrant.
    """
    results: list[dict] = []
    if store is None:
        return results

    q_emb = None
    if query:
        try:
            embs = embed_texts([query])
            if embs:
                q_emb = embs[0]
        except Exception:
            q_emb = None

    # --- macro: chapter wikis ---
    top_chapter_ids: set[str] = set()
    if layer in ("macro", "all"):
        chapter_wikis = store.get_chapter_wikis_by_course(course_id)
        scored_chapters = []
        for cw in chapter_wikis:
            text = f"{cw.title} {cw.overview} {' '.join(cw.key_concepts)}"
            ch_emb = _get_chapter_embedding(text)
            if q_emb is not None and ch_emb is not None:
                score = _cosine_similarity(q_emb, ch_emb)
            else:
                score = 0.0
            if score > 0.1:
                scored_chapters.append((score, cw))
                results.append({
                    "id": cw.id,
                    "name": cw.title,
                    "layer": "macro",
                    "score": score,
                    "content": cw.overview,
                    "source_ref": f"[{cw.title}]",
                    "file_name": "",
                    "locator": cw.title,
                })
        # Top-2 chapters for cascade boosting
        scored_chapters.sort(key=lambda x: x[0], reverse=True)
        top_chapter_ids = {cw.chapter_id for _, cw in scored_chapters[:2]}

    # --- micro: KCs with chapter-cascade boost ---
    if layer in ("micro", "all"):
        kcs = store.get_kcs_by_course(course_id)
        kcs_with_emb = [kc for kc in kcs if kc.embedding is not None]
        kcs_without_emb = [kc for kc in kcs if kc.embedding is None]

        if q_emb is not None:
            for kc in kcs_with_emb:
                base_score = _cosine_similarity(q_emb, kc.embedding)
                boost = 0.15 if kc.chapter_id in top_chapter_ids else 0.0
                score = min(1.0, base_score + boost)
                if score > 0.1:
                    results.append({
                        "id": kc.id,
                        "name": kc.name,
                        "layer": kc.layer,
                        "score": score,
                        "content": kc.definition,
                        "source_ref": kc.source_refs[0].file if kc.source_refs else "",
                        "file_name": kc.source_refs[0].file if kc.source_refs else "",
                        "locator": kc.chapter_id,
                    })
        else:
            kcs_without_emb = kcs

            # KCs without stored embeddings: compute on-demand
            for kc in kcs_without_emb:
                text = f"{kc.name} {kc.definition} {kc.formula}"
                kc_emb = _get_chapter_embedding(text)
                if kc_emb is not None:
                    score = _cosine_similarity(q_emb, kc_emb)
                    if score > 0.1:
                        results.append({
                            "id": kc.id,
                            "name": kc.name,
                            "layer": kc.layer,
                            "score": score,
                            "content": kc.definition,
                            "source_ref": kc.source_refs[0].file if kc.source_refs else "",
                            "file_name": kc.source_refs[0].file if kc.source_refs else "",
                            "locator": kc.chapter_id,
                        })

        # Notes only (no raw chunks)
        if q_emb is not None and (selected_note_ids or not selected_material_ids):
            from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue
            note_conditions = [FieldCondition(key="type", match=MatchValue(value="note"))]
            if selected_note_ids:
                note_conditions.append(
                    FieldCondition(key="note_id", match=MatchAny(any=selected_note_ids))
                )
            note_filter = Filter(must=note_conditions)
            note_results = _qdrant.search(course_id, q_emb, limit=top_k, query_filter=note_filter)
            for r in note_results:
                payload = r.get("payload", {})
                note_title = payload.get("title", "")
                results.append({
                    "id": payload.get("note_id", ""),
                    "name": note_title,
                    "layer": "note",
                    "score": r.get("score", 0),
                    "content": payload.get("text", ""),
                    "source_ref": f"笔记 · {note_title}",
                    "file_name": "笔记",
                    "locator": note_title,
                    "is_note": True,
                })

    if layer == "all":
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        seen: set[tuple] = set()
        deduped = []
        for r in results:
            key = (r.get("id", ""), r.get("file_name", ""), r.get("locator", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(r)
        results = deduped

        # Fallback: if best KC score is too low, search raw parsed texts
        max_kc_score = max((r["score"] for r in results if r.get("layer") != "note"), default=0)
        if max_kc_score < 0.55 and store is not None:
            raw_hits = _search_raw_texts(course_id, query, store, top_k=top_k)
            if raw_hits:
                results = sorted(results + raw_hits, key=lambda x: x.get("score", 0), reverse=True)

    return results[:top_k]


def _search_raw_texts(
    course_id: str,
    query: str,
    store: Any,
    top_k: int = 5,
) -> list[dict]:
    """Fallback: split parsed texts into paragraphs and return best matching ones."""
    import re
    all_parsed = store.get_all_parsed_texts(course_id)
    # Break query into individual terms for matching (handle multi-word queries)
    query_terms = [t.strip() for t in re.split(r'\s+', query) if len(t.strip()) >= 2]
    candidates = []
    for mat_id, text in all_parsed.items():
        # Split into paragraphs by double newlines or timestamps
        chunks = re.split(r'\n{2,}|\[\s*[\d.]+min\]', text)
        for chunk in chunks:
            chunk = chunk.strip()
            if len(chunk) < 20:
                continue
            # Check how many query terms appear in this chunk
            matched = sum(1 for t in query_terms if t in chunk)
            if matched == len(query_terms) and matched > 0:
                # All terms found — high confidence
                candidates.append((0.80, chunk[:500]))
            elif matched > 0:
                # Partial match — proportional confidence
                candidates.append((0.60 * matched / max(len(query_terms), 1), chunk[:500]))
            else:
                # Character overlap fallback
                score = _text_overlap_score(query, chunk[:200])
                if score > 0.2:
                    candidates.append((score * 0.7, chunk[:500]))

    candidates.sort(key=lambda x: x[0], reverse=True)
    return [
        {
            "id": f"raw-{i}",
            "name": "原文片段",
            "layer": "raw",
            "score": round(score, 3),
            "content": text,
            "source_ref": "原始材料",
            "file_name": "原始材料",
            "locator": "",
        }
        for i, (score, text) in enumerate(candidates[:top_k])
    ]


def search_term_layer(course_id: str, query: str, top_k: int = 5) -> list[dict]:
    """Search domain terminology dictionary (Qdrant type=term). Returns [{name, definition, score, layer}]."""
    from app.services.terminology import search_terms
    return search_terms(course_id, query, top_k=top_k)
