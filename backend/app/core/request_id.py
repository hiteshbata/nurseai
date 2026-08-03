import logging
import uuid
from contextvars import ContextVar

import sentry_sdk

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def get_request_id() -> str:
    return _request_id_ctx.get()


class RequestIDLogFilter(logging.Filter):
    """Attaches the current request's ID to every LogRecord as %(request_id)s."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class RequestIDMiddleware:
    """Reads X-Request-ID off the incoming request (the frontend generates
    one per call) or generates a uuid4 if absent, exposes it to logging/Sentry
    for the life of the request, and echoes it back on the response so both
    sides can be correlated for a single call.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id")
        request_id = incoming.decode() if incoming else str(uuid.uuid4())
        token = _request_id_ctx.set(request_id)
        sentry_sdk.set_tag("request_id", request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + [
                    (b"x-request-id", request_id.encode())
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _request_id_ctx.reset(token)
