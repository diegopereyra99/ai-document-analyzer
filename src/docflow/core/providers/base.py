"""Provider abstraction."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..models.schema_defs import InternalSchema


@dataclass
class ProviderOptions:
    model_name: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None

    def merged(self, override: "ProviderOptions | None") -> "ProviderOptions":
        if override is None:
            return self
        return ProviderOptions(
            model_name=override.model_name or self.model_name,
            temperature=self.temperature if override.temperature is None else override.temperature,
            max_output_tokens=self.max_output_tokens
            if override.max_output_tokens is None
            else override.max_output_tokens,
        )


class ModelProvider(Protocol):
    last_usage: dict | None
    last_model: str | None

    def generate_structured(
        self,
        prompt: str,
        schema: InternalSchema,
        options: ProviderOptions | None = None,
        system_instruction: str | None = None,
        attachments: list[tuple[str, bytes | str]] | None = None,
    ) -> dict:
        ...
