"""Server-Sent Events helpers.

``StreamingResponse`` cancels its body iterator when the client disconnects, but
it never closes a *synchronous* generator: the generator is advanced through a
thread pool, and the pending ``next()`` call cannot be interrupted. A suspended
generator is only closed when it is garbage collected, which may never happen
while the abandoned worker still references it. For an execution stream that
means the run stays ``running`` forever after the caller hangs up.

The wrapper below owns the synchronous iterator in one dedicated producer
thread. That thread is also the one that calls ``close()``, which is required
because the iterator creates and uses its own database session (sessions must
not cross threads, and a generator cannot be closed from another thread while
it is executing). Disconnect therefore becomes a cooperative stop: the producer
stops at the next event, closes the iterator, and the execution finalizes itself
as ``cancelled``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from collections.abc import AsyncIterator, Iterable, Iterator
from typing import Any

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.providers.base import StreamEvent

logger = logging.getLogger("app.sse")

# How long the consumer waits for a chunk before checking for a disconnect. A
# provider that is thinking (no tokens yet) must not delay cancellation.
POLL_SECONDS = 0.2
# How long the producer may block on a full queue before re-checking ``stop``.
PUT_TIMEOUT_SECONDS = 0.2
# Upper bound on how long a disconnect handler waits for the producer to finish.
JOIN_TIMEOUT_SECONDS = 5.0

_DONE = object()


def format_sse_event(event: StreamEvent) -> str:
    payload = {"type": event.type, "text": event.text, "data": event.data}
    return f"event: {event.type}\ndata: {json.dumps(payload, default=str)}\n\n"


def format_sse(events: Iterable[StreamEvent]) -> Iterator[str]:
    for event in events:
        yield format_sse_event(event)


def _offer(target: queue.Queue[Any], item: object) -> None:
    """Put without ever blocking, for terminal signals."""
    try:
        target.put_nowait(item)
    except queue.Full:
        pass


def _put(target: queue.Queue[Any], item: object, stop: threading.Event) -> bool:
    """Put with a bounded wait so a vanished consumer cannot wedge the thread."""
    while not stop.is_set():
        try:
            target.put(item, timeout=PUT_TIMEOUT_SECONDS)
            return True
        except queue.Full:
            continue
    return False


def _produce(
    events: Iterator[StreamEvent],
    out: queue.Queue[Any],
    stop: threading.Event,
) -> None:
    """Drain ``events`` in this thread and hand formatted frames to ``out``."""
    try:
        for event in events:
            if stop.is_set():
                break
            if not _put(out, format_sse_event(event), stop):
                break
    except BaseException:  # noqa: BLE001 - the stream must still be closed
        logger.exception("SSE producer failed while reading the event stream")
    finally:
        # Runs in the producer thread, which is the only thread allowed to
        # close this generator. ``GeneratorExit`` reaches the execution
        # generator here, so it can record the terminal run state.
        try:
            events.close()
        except BaseException:  # noqa: BLE001 - never mask the stream ending
            logger.exception("SSE producer failed while closing the event stream")
        _offer(out, _DONE)


async def _consume(
    events: Iterator[StreamEvent],
    request: Request | None,
) -> AsyncIterator[str]:
    out: queue.Queue[Any] = queue.Queue(maxsize=128)
    stop = threading.Event()
    producer = threading.Thread(
        target=_produce,
        args=(events, out, stop),
        name="sse-producer",
        daemon=True,
    )
    producer.start()
    try:
        while True:
            try:
                item = await asyncio.to_thread(out.get, True, POLL_SECONDS)
            except queue.Empty:
                if request is not None and await request.is_disconnected():
                    break
                continue
            if item is _DONE:
                break
            yield item
            if request is not None and await request.is_disconnected():
                break
    finally:
        stop.set()
        # Wake a producer that is blocked on a full queue.
        _offer(out, _DONE)
        try:
            # Shielded: the caller may already be cancelled, but a stream that
            # is closed promptly is worth waiting a moment for.
            await asyncio.shield(asyncio.to_thread(producer.join, JOIN_TIMEOUT_SECONDS))
        except BaseException:  # noqa: BLE001 - best effort only
            logger.debug("SSE producer did not join before the response ended")


def event_stream_response(
    events: Iterable[StreamEvent],
    *,
    request: Request | None = None,
) -> StreamingResponse:
    """Build an SSE response that finalizes the run when the client hangs up."""
    return StreamingResponse(
        _consume(iter(events), request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
