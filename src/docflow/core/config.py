"""Core defaults (no environment reads)."""
from dataclasses import dataclass
from typing import Optional

DEFAULT_MODEL_NAME = "gemini-2.5-flash"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_OUTPUT_TOKENS: Optional[int] = None
DEFAULT_MULTI_MODE = "per_file"
MAX_DOCS_PER_EXTRACTION = 16


@dataclass
class CoreDefaults:
    model_name: str = DEFAULT_MODEL_NAME
    temperature: float = DEFAULT_TEMPERATURE
    max_output_tokens: Optional[int] = DEFAULT_MAX_OUTPUT_TOKENS
    multi_mode: str = DEFAULT_MULTI_MODE
    max_docs: int = MAX_DOCS_PER_EXTRACTION


DEFAULTS = CoreDefaults()
