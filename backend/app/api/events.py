import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from app.db.deps import get_store
from app.db.sqlite_store import SqliteStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/courses/{course_id}/events")

_event_queues: dict[str, asyncio.Queue[dict]] = {}
_stream_counts: dict[str, int] = {}


def _get_queue(course_id: str) -> asyncio.Queue[dict]:
    if course_id not in _event_queues:
        _event_queues[course_id] = asyncio.Queue(maxsize=100)
    return _event_queues[course_id]


def push_event(course_id: str, event_type: str, data: dict) -> None:
    queue = _get_queue(course_id)
    try:
        queue.put_nowait({"event": event_type, "data": data})
    except asyncio.QueueFull:
        logger.warning("Event queue full for course %s, dropping event %s", course_id, event_type)


@router.get("")
async def stream_events(course_id: str, request: Request):
    queue = _get_queue(course_id)
    _stream_counts[course_id] = _stream_counts.get(course_id, 0) + 1

    async def generator():
        # Send initial connection event
        yield f"event: connected\ndata: {json.dumps({})}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    event_type = event.get("event", "message")
                    event_data = json.dumps(event.get("data", {}), ensure_ascii=False)
                    yield f"event: {event_type}\ndata: {event_data}\n\n"
                except asyncio.TimeoutError:
                    yield f"event: ping\ndata: {json.dumps({})}\n\n"
        finally:
            _stream_counts[course_id] = max(0, _stream_counts.get(course_id, 1) - 1)
            if _stream_counts.get(course_id, 0) <= 0:
                _event_queues.pop(course_id, None)
                _stream_counts.pop(course_id, None)

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
