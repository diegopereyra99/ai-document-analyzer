"""Extraction orchestrator."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence

from .. import config
from ..errors import DocumentError, ExtractionError
from ..models.documents import DocSource, load_content
from ..models.profiles import ExtractionProfile
from ..models.schema_defs import InternalSchema, normalize_output, parse_schema, validate_output
from ..providers.base import ModelProvider, ProviderOptions
from ..providers.gemini import GeminiProvider


@dataclass
class ExtractionResult:
    data: dict
    meta: dict

    def to_dict(self) -> dict:
        return {"data": self.data, "meta": self.meta}


@dataclass
class MultiResult:
    per_file: List[ExtractionResult]
    aggregate: ExtractionResult | None = None

    def to_dict(self) -> dict:
        return {
            "per_file": [r.to_dict() for r in self.per_file],
            "aggregate": self.aggregate.to_dict() if self.aggregate else None,
        }


# --- internal helpers ---

def _resolve_schema(schema: InternalSchema | dict | None, profile: ExtractionProfile | None) -> InternalSchema | None:
    candidate = None
    if profile and profile.schema is not None:
        candidate = profile.schema
    elif isinstance(schema, dict):
        candidate = parse_schema(schema)
    elif isinstance(schema, InternalSchema):
        candidate = schema

    return candidate


def _resolve_multi_mode(profile: ExtractionProfile | None, multi_mode: str | None) -> str:
    mode = multi_mode or (profile.multi_mode_default if profile else None) or config.DEFAULT_MULTI_MODE
    if mode not in {"per_file", "aggregate", "both"}:
        raise ExtractionError(f"Invalid multi-mode: {mode}")
    return mode


def _merge_options(profile: ExtractionProfile | None, options: ProviderOptions | None) -> ProviderOptions | None:
    base = ProviderOptions(
        model_name=config.DEFAULT_MODEL_NAME,
        temperature=config.DEFAULT_TEMPERATURE,
        max_output_tokens=config.DEFAULT_MAX_OUTPUT_TOKENS,
    )
    if profile and profile.provider_options:
        base = base.merged(profile.provider_options)
    if options:
        base = base.merged(options)
    return base


def _build_prompt(profile: ExtractionProfile | None, aggregate: bool) -> tuple[str, str]:
    """Compose minimal prompt and system instruction from profile."""
    # System instruction: prefer profile value, otherwise safe default
    system_instruction = (
        profile.system_instruction
        if profile and profile.system_instruction
        else "Return JSON that matches the provided schema. Use null for missing values. Do not add extra text."
    )

    lines: List[str] = []
    if profile and profile.prompt:
        lines.append(profile.prompt)
    elif profile and profile.description:
        lines.append(profile.description)
    else:
        if profile and profile.mode == "describe":
            lines.append("Provide a concise description of the document content.")
        elif profile and profile.name == "extract_all":
            lines.append("Extract all salient structured data you can find.")
        else:
            lines.append("Extract the requested structured fields. Use null for missing values.")

    if aggregate:
        lines.append("Multiple documents provided.")

    prompt = "\n\n".join(lines)
    return prompt, system_instruction


def _provider_or_default(provider: ModelProvider | None) -> ModelProvider:
    return provider if provider is not None else GeminiProvider()


def _single_call(
    provider: ModelProvider,
    prompt: str,
    internal_schema: InternalSchema | None,
    options: ProviderOptions | None,
    doc_names: List[str],
    mode: str,
    profile: ExtractionProfile | None,
    system_instruction: str,
    attachments: list[tuple[str, bytes | str]],
) -> ExtractionResult:
    data = provider.generate_structured(
        prompt=prompt,
        schema=internal_schema,
        options=options,
        system_instruction=system_instruction,
        attachments=attachments,
    )
    if internal_schema is not None:
        validate_output(internal_schema, data)
        payload = normalize_output(internal_schema, data)
    else:
        payload = data
    meta = {
        "model": getattr(provider, "last_model", None) or (options.model_name if options else None),
        "usage": getattr(provider, "last_usage", None),
        "docs": doc_names,
        "mode": mode,
        "profile": profile.name if profile else None,
    }
    return ExtractionResult(data=payload, meta=meta)


# --- public API ---

def extract(
    docs: List[DocSource],
    schema: InternalSchema | dict | None = None,
    profile: ExtractionProfile | None = None,
    provider: ModelProvider | None = None,
    options: ProviderOptions | None = None,
    multi_mode: str | None = None,
) -> ExtractionResult | List[ExtractionResult] | MultiResult:
    if not docs:
        raise DocumentError("No documents provided")
    if len(docs) > config.MAX_DOCS_PER_EXTRACTION:
        raise ExtractionError("Too many documents for a single extraction")

    internal_schema = _resolve_schema(schema, profile)
    mode = _resolve_multi_mode(profile, multi_mode)
    eff_options = _merge_options(profile, options)
    provider_inst = _provider_or_default(provider)

    loaded_docs: List[tuple[str, bytes | str]] = []
    for doc in docs:
        content = load_content(doc)
        loaded_docs.append((doc.display_name(), content))
    attachments = loaded_docs

    results: List[ExtractionResult] = []

    if mode in {"per_file", "both"}:
        for name, content in loaded_docs:
            prompt, sys_inst = _build_prompt(profile, aggregate=False)
            results.append(
                _single_call(
                    provider_inst,
                    prompt,
                    internal_schema,
                    eff_options,
                    [name],
                    mode="per_file",
                    profile=profile,
                    system_instruction=sys_inst,
                    attachments=[(name, content)],
                )
            )

    aggregate_result: ExtractionResult | None = None
    if mode in {"aggregate", "both"}:
        prompt, sys_inst = _build_prompt(profile, aggregate=True)
        aggregate_result = _single_call(
            provider_inst,
            prompt,
            internal_schema,
            eff_options,
            [name for name, _ in loaded_docs],
            mode="aggregate",
            profile=profile,
            system_instruction=sys_inst,
            attachments=attachments,
        )

    if mode == "per_file":
        return results
    if mode == "aggregate":
        return aggregate_result or ExtractionResult(data={}, meta={})
    return MultiResult(per_file=results, aggregate=aggregate_result)
