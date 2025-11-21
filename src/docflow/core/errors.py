"""Core exception hierarchy."""

class DocflowError(Exception):
    """Base class for DocFlow errors."""


class SchemaError(DocflowError):
    """Schema parsing or validation error."""


class ProfileError(DocflowError):
    """Profile configuration error."""


class ProviderError(DocflowError):
    """LLM provider error."""


class ExtractionError(DocflowError):
    """Orchestration or extraction error."""


class DocumentError(DocflowError):
    """Document loading or handling error."""
