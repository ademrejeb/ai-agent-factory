"""Streaming request-body cap that also works without Content-Length."""

from __future__ import annotations

PAYLOAD_TOO_LARGE = (
    b'{"error":{"code":"payload_too_large","message":"Request body exceeds the configured limit.","details":{}}}'
)


class BodySizeLimitMiddleware:
    def __init__(self, app, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        received = 0
        rejected = False
        response_started = False

        async def guarded_send(message) -> None:
            nonlocal response_started
            if rejected:
                return
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        async def limited_receive():
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] != "http.request":
                return message
            received += len(message.get("body", b""))
            if received <= self.max_bytes:
                return message
            if not response_started:
                rejected = True
                await send(
                    {
                        "type": "http.response.start",
                        "status": 413,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(PAYLOAD_TOO_LARGE)).encode()),
                            (b"connection", b"close"),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": PAYLOAD_TOO_LARGE})
            return {"type": "http.disconnect"}

        await self.app(scope, limited_receive, guarded_send)
