"""Typed failures. Application services raise these; the API maps each to one response shape.
Routes never catch broadly and never invent their own status codes."""

from __future__ import annotations


class WorkbenchError(Exception):
    status_code = 500


class NotFound(WorkbenchError):
    status_code = 404

    def __init__(self, kind: str, identifier: str) -> None:
        super().__init__(f"{kind} not found")
        self.kind = kind
        self.identifier = identifier


class Conflict(WorkbenchError):
    """The request is well-formed but the record is not in a state that allows it."""

    status_code = 409


class InvalidInput(WorkbenchError):
    """The input cannot be used: an unsupported or unreadable file, for example."""

    status_code = 422


class TooLarge(WorkbenchError):
    status_code = 413


class Busy(WorkbenchError):
    """The store is held by another write for longer than a request waits; nothing was written, and a retry may pass."""

    status_code = 503


class AccessRequired(WorkbenchError):
    """No valid session: the reader has not come through an invite, or the session has ended."""

    status_code = 401


class Forbidden(WorkbenchError):
    status_code = 403


class TooManyRequests(WorkbenchError):
    status_code = 429

    def __init__(self, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.retry_after = retry_after
