"""Error handling.

Users only ever see a plain-English message (Spec §29). Unexpected failures are logged with
an error ID that is also returned to the client, so an administrator can quote it to support
without a stack trace ever reaching the browser.
"""

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("policy_compass")

GENERIC_MESSAGE = "Something went wrong. Please try again."


class AppError(Exception):
    """An expected error with a message that is safe to show to the user."""

    def __init__(self, status_code: int, code: str, message: str, fields: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields or {}


class PermissionDenied(AppError):
    def __init__(self, message: str = "You don't have permission to do this."):
        super().__init__(403, "permission_denied", message)


class NotFound(AppError):
    def __init__(self, message: str = "This item is no longer available."):
        super().__init__(404, "not_found", message)


def _body(code: str, message: str, fields: dict | None = None, error_id: str | None = None):
    error = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    if error_id:
        error["error_id"] = error_id
    return {"error": error}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code, content=_body(exc.code, exc.message, exc.fields)
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            fields[".".join(loc) or "request"] = err["msg"].removeprefix("Value error, ")
        return JSONResponse(
            status_code=422,
            content=_body("validation_error", "Please check the highlighted fields.", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http(_: Request, exc: StarletteHTTPException):
        messages = {404: "This page or item could not be found.", 405: "This action isn't allowed."}
        message = messages.get(exc.status_code, GENERIC_MESSAGE)
        return JSONResponse(status_code=exc.status_code, content=_body("http_error", message))

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:12]
        logger.exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
        return JSONResponse(
            status_code=500, content=_body("internal_error", GENERIC_MESSAGE, error_id=error_id)
        )
