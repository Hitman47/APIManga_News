class ApiError(Exception):
    """Base application error."""


class UpstreamError(ApiError):
    """Raised when Manga News fails or returns unexpected content."""


class ParseError(ApiError):
    """Raised when an upstream response cannot be parsed reliably."""


class BadRequestError(ApiError):
    """Raised when the caller sends invalid request parameters."""


class ResourceNotFound(ApiError):
    """Raised when the requested resource does not exist."""
