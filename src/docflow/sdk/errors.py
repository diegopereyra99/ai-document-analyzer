"""SDK-level errors."""

class SdkError(Exception):
    """Base SDK error."""


class RemoteServiceError(SdkError):
    """HTTP/service communication error."""


class ConfigError(SdkError):
    """Configuration resolution error."""
