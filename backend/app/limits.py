"""Request body size limit (US-038).

Uploads are refused as soon as they exceed the limit, before the multipart parser can spool a
huge body to disk: a declared Content-Length over the limit is refused immediately, and bodies
without one (chunked) are counted as they arrive and cut off at the limit.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class _BodyTooLarge(Exception):
    pass


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int, file_limit_mb: int = 20):
        self.app = app
        self.max_bytes = max_bytes
        self.too_large = {
            "error": {
                "code": "too_large",
                "message": (
                    f"This upload is too large. Files must be {file_limit_mb} MB or smaller."
                ),
            }
        }

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS", "DELETE"):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        declared = headers.get(b"content-length")
        if declared is not None:
            try:
                if int(declared) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                await self._reject(send, status=400)
                return

        received = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except _BodyTooLarge:
            if not started:
                await self._reject(send)

    async def _reject(self, send: Send, status: int = 413) -> None:
        body = json.dumps(
            self.too_large
            if status == 413
            else {
                "error": {
                    "code": "bad_request",
                    "message": "Something went wrong. Please try again.",
                }
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": status,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
