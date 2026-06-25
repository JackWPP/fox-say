import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore
from app.schemas.foxsay import CreateNoteRequest, Note, UpdateNoteRequest
from app.services.embedding import embed_text
from app.services.vectorstore import QdrantStore

router = APIRouter(prefix="/courses/{course_id}/notes")

_qdrant = QdrantStore()


@router.post("", response_model=Note)
async def create_note(
    course_id: str,
    body: CreateNoteRequest,
    store: SqliteStore = Depends(get_store),
):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    note_id = str(uuid.uuid4())
    note = Note(
        id=note_id,
        course_id=course_id,
        title=body.title,
        content=body.content,
        source_citations=body.source_citations,
    )
    created = store.create_note(note)

    try:
        embedding = embed_text(f"{body.title}\n{body.content}")
        if embedding:
            _qdrant.upsert_note(course_id, note_id, body.title, body.content, embedding)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to embed note %s", note_id)
        raise HTTPException(status_code=500, detail="Failed to process note embedding")

    return created


@router.get("", response_model=list[Note])
async def list_notes(course_id: str, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return store.get_notes_by_course(course_id)


@router.get("/{note_id}", response_model=Note)
async def get_note(course_id: str, note_id: str, store: SqliteStore = Depends(get_store)):
    note = store.get_note(course_id, note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Note not found")
    return note


@router.patch("/{note_id}", response_model=Note)
async def update_note(
    course_id: str,
    note_id: str,
    body: UpdateNoteRequest,
    store: SqliteStore = Depends(get_store),
):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    existing = store.get_note(course_id, note_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Note not found")

    update_kwargs: dict = {}
    if body.title is not None:
        update_kwargs["title"] = body.title
    if body.content is not None:
        update_kwargs["content"] = body.content
    if body.source_citations is not None:
        update_kwargs["source_citations"] = body.source_citations

    updated = store.update_note(course_id, note_id, **update_kwargs)
    if updated is None:
        raise HTTPException(status_code=404, detail="Note not found")

    new_title = body.title if body.title is not None else existing.title
    new_content = body.content if body.content is not None else existing.content
    if body.title is not None or body.content is not None:
        try:
            embedding = embed_text(f"{new_title}\n{new_content}")
            if embedding:
                _qdrant.upsert_note(course_id, note_id, new_title, new_content, embedding)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Failed to re-embed note %s", note_id)
            raise HTTPException(status_code=500, detail="Failed to process note embedding")

    return updated


@router.delete("/{note_id}")
async def delete_note(course_id: str, note_id: str, store: SqliteStore = Depends(get_store)):
    course = store.get_course(course_id)
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")

    deleted = store.delete_note(course_id, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Note not found")

    try:
        _qdrant.delete_note(course_id, note_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Failed to delete note vector %s", note_id)

    return {"deleted": True}
