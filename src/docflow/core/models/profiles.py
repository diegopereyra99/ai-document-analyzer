"""Extraction profiles."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from ..providers.base import ProviderOptions
from .schema_defs import InternalSchema


@dataclass
class ExtractionProfile:
    name: str
    schema: InternalSchema | None
    mode: Literal["extract", "extract_all", "describe"]
    multi_mode_default: Literal["per_file", "aggregate", "both"] = "per_file"
    description: Optional[str] = None
    provider_options: Optional[ProviderOptions] = None
    prompt: Optional[str] = None
    system_instruction: Optional[str] = None
    params: Optional[dict[str, Any]] = None
