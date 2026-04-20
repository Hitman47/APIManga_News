from __future__ import annotations


class ApiError(Exception):
    """Base application error with a stable machine-readable code."""

    code = 'API_ERROR'

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class UpstreamError(ApiError):
    """Raised when Manga News fails or returns unexpected content."""

    code = 'UPSTREAM_FETCH_ERROR'


class ParseError(ApiError):
    """Raised when an upstream response cannot be parsed reliably."""

    code = 'UPSTREAM_PARSE_ERROR'

    def __init__(self, detail: str, *, debug_dump_path: str | None = None):
        super().__init__(detail)
        self.debug_dump_path = debug_dump_path


class BadRequestError(ApiError):
    """Raised when the caller sends invalid request parameters."""

    code = 'INVALID_REQUEST'


class ResourceNotFound(ApiError):
    """Raised when the requested resource does not exist."""

    code = 'RESOURCE_NOT_FOUND'
