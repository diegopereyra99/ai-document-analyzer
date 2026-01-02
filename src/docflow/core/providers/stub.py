"""Stub provider for local/dev schema-shaped outputs.

Generates minimal payloads that satisfy InternalSchema validation:
- Global fields present with value None
- Record sets present as empty lists
"""
from __future__ import annotations

from typing import Any, List, Tuple

from .base import ModelProvider, ProviderOptions
from ..models.schema_defs import InternalSchema


class StubProvider(ModelProvider):
    def __init__(self, model_name: str = "stub-model") -> None:
        self.last_usage = {"note": "stub"}
        self.last_model = model_name

    def generate_structured(
        self,
        prompt: str,
        schema: InternalSchema | None,
        options: ProviderOptions | None = None,
        system_instruction: str | None = None,
        attachments: list[tuple[str, bytes | str]] | None = None,
    ) -> dict:
        if schema is None:
            return {}
        out: dict = {}
        for f in schema.global_fields:
            out[f.name] = None
        for rs in schema.record_sets:
            out[rs.name] = []
        return out

