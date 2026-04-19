class ApiError(Exception):
    """Base application error."""


class UpstreamError(ApiError):
    """Raised when Manga News fails or returns unexpected content."""


class ParseError(ApiError):
    """Raised when a response cannot be parsed reliably."""


class ResourceNotFound(ApiError):
    """Raised when the requested resource does not exist."""
