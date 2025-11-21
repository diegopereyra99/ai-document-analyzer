"""HTTP handler for /extract-data."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status

from docflow.core.errors import DocumentError, ExtractionError, ProfileError, ProviderError, SchemaError
from docflow.core.extraction.engine import ExtractionResult, MultiResult, extract
from docflow.core.models.documents import FileSource, GcsSource
from docflow.core.models.schema_defs import InternalSchema, parse_schema
from docflow.core.providers.base import ProviderOptions
from docflow.sdk.profiles import load_profile, BUILTIN_PROFILES

from ..config import ServiceConfig, load_service_config
from ..dependencies import get_logger, get_provider

router = APIRouter()


def _make_sources(files: List[Dict[str, Any]]) -> List[FileSource | GcsSource]:
    sources: List[FileSource | GcsSource] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        uri = item.get("uri") or item.get("gcs_uri")
        if isinstance(uri, str) and uri.startswith("gs://"):
            sources.append(GcsSource(uri=uri))
        elif isinstance(uri, str):
            sources.append(FileSource(Path(uri)))
    return sources


def _options_from_payload(data: dict | None) -> ProviderOptions | None:
    if not data:
        return None
    return ProviderOptions(
        model_name=data.get("model_name"),
        temperature=data.get("temperature"),
        max_output_tokens=data.get("max_output_tokens"),
    )


def _result_to_obj(result: Any) -> Any:
    if isinstance(result, MultiResult):
        return result.to_dict()
    if isinstance(result, ExtractionResult):
        return result.to_dict()
    if isinstance(result, list):
        return [_result_to_obj(r) for r in result]
    return result


@router.post("/extract-data")
def extract_data(payload: Dict[str, Any], cfg: ServiceConfig = Depends(load_service_config)) -> Dict[str, Any]:
    logger = get_logger()
    schema_val = payload.get("schema")
    profile_name = payload.get("profile")
    files_val = payload.get("files") or []
    multi_mode = payload.get("multi")

    profile = None
    internal_schema: InternalSchema | None = None
    if profile_name:
        profile = load_profile(profile_name)
        internal_schema = profile.schema
    if internal_schema is None and isinstance(schema_val, dict):
        internal_schema = parse_schema(schema_val)

    if internal_schema is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="schema is required")

    sources = _make_sources(files_val)
    provider = get_provider(cfg)
    options = _options_from_payload(payload.get("options"))

    try:
        result = extract(
            docs=sources,
            schema=internal_schema,
            profile=profile or BUILTIN_PROFILES.get(profile_name or ""),
            provider=provider,
            options=options,
            multi_mode=multi_mode,
        )
    except SchemaError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except ProfileError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc

    response: Dict[str, Any] = {
        "ok": True,
        "data": _result_to_obj(result),
        "meta": {
            "model": getattr(provider, "last_model", None) or cfg.default_model,
        },
    }
    logger.info("Handled extraction with %s document(s)", len(sources))
    return response
