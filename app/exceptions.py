"""
Custom exceptions for the OpenManus application.
"""

class OpenManusError(Exception):
    """Base class for all OpenManus exceptions."""
    pass


class TokenLimitExceeded(OpenManusError):
    """Raised when token limits are exceeded."""
    pass


class RateLimitExceeded(OpenManusError):
    """Raised when API rate limits are exceeded."""
    pass


class ToolUnavailableError(OpenManusError):
    """Raised when a tool is not available."""
    pass


class EndpointError(OpenManusError):
    """Raised when an endpoint returns an error."""
    pass


class ToolExecutionError(OpenManusError):
    """Raised when a tool execution fails."""
    pass


class ToolError(OpenManusError):
    """Raised when there is an error with a tool."""
    pass


class ParsingError(OpenManusError):
    """Raised when parsing fails."""
    pass
