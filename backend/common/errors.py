"""Shared error types + a route class that maps failures to clean JSON responses.

The mapping is applied ONLY to hub routes (via `route_class=HubRoute`), so the
rest of the Casefile API keeps FastAPI's default behaviour.

    400 invalid request   404 not found   409 conflict
    503 database unavailable / not configured   500 anything else (no internals leaked)
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pymongo.errors import ConnectionFailure, DuplicateKeyError, PyMongoError

log = logging.getLogger("hub")


class ApiError(Exception):
    """A client-facing error with an HTTP status."""

    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def _json(status: int, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": message, **extra})


class HubRoute(APIRoute):
    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except ApiError as exc:
                return _json(exc.status_code, exc.message)
            except RequestValidationError as exc:
                problems = [
                    {"field": ".".join(str(p) for p in e["loc"] if p not in ("query", "body", "path")), "message": e["msg"]}
                    for e in exc.errors()
                ]
                return _json(400, "Invalid request", errors=problems)
            except HTTPException:
                raise  # FastAPI's normal handling
            except DuplicateKeyError:
                return _json(409, "An event with the same identity already exists")
            except ConnectionFailure:
                log.error("MongoDB unavailable while serving %s", request.url.path)
                return _json(503, "Database temporarily unavailable")
            except PyMongoError:
                log.exception("Database error on %s", request.url.path)
                return _json(500, "Internal server error")
            except Exception:  # noqa: BLE001 - never leak internals to the client
                log.exception("Unhandled error on %s", request.url.path)
                return _json(500, "Internal server error")

        return handler
