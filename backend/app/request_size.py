"""Bound buffered HTTP request bodies before FastAPI parses JSON."""

import json
import re
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

ASGIApp = Callable[
    [dict[str, Any], Callable[..., Awaitable[dict[str, Any]]], Callable[..., Awaitable[None]]],
    Awaitable[None],
]
REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z")


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int):
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                await self._reject(scope, send, 400, "Invalid Content-Length header.")
                return
            if declared_length < 0:
                await self._reject(scope, send, 400, "Invalid Content-Length header.")
                return
            if declared_length > self.max_body_bytes:
                await self._reject(
                    scope, send, 413, "Request body exceeds the configured size limit."
                )
                return

        messages: list[dict[str, Any]] = []
        body_size = 0
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                continue
            body_size += len(message.get("body", b""))
            if body_size > self.max_body_bytes:
                await self._reject(
                    scope, send, 413, "Request body exceeds the configured size limit."
                )
                return
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive():
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, scope, send, status_code: int, message: str) -> None:
        request_headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied_id = request_headers.get(b"x-request-id", b"").decode("latin-1")
        state = scope.get("state")
        scoped_id = state.get("request_id", "") if isinstance(state, dict) else ""
        if REQUEST_ID_PATTERN.fullmatch(scoped_id):
            # The outer request-ID middleware owns the response header. Reuse its
            # validated value so an early body rejection has one support reference.
            request_id = scoped_id
        else:
            request_id = (
                supplied_id if REQUEST_ID_PATTERN.fullmatch(supplied_id) else str(uuid.uuid4())
            )
        body = json.dumps(
            {
                "error": {
                    "code": "request_too_large" if status_code == 413 else "invalid_request",
                    "message": message,
                    "request_id": request_id,
                }
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": status_code,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"x-request-id", request_id.encode("latin-1", errors="replace")),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"strict-origin-when-cross-origin"),
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
