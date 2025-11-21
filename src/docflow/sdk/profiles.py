"""Profile resolution for SDK and CLI."""
from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Dict, List

import yaml

from docflow.core.errors import ProfileError
from docflow.core.models.profiles import ExtractionProfile
from docflow.core.models.schema_defs import InternalSchema, parse_schema
from docflow.core.providers.base import ProviderOptions
from docflow.core.utils.io import load_structured
from .config import SdkConfig

PROFILE_EXTS = [".yaml", ".yml", ".json"]
BUILTIN_PACKAGE = "docflow.sdk.builtin_profiles"


def _as_path(traversable) -> Path:
    try:
        return Path(traversable)  # type: ignore[arg-type]
    except TypeError:
        with resources.as_file(traversable) as temp_path:
            return temp_path


def _profile_dirs(config: SdkConfig | None = None) -> List[Path]:
    dirs: List[Path] = []
    cwd = Path.cwd()
    project_dir = cwd / ".docflow" / "profiles"
    if project_dir.exists():
        dirs.append(project_dir)
    if config and config.profile_dir:
        dirs.append(config.profile_dir)
    user_dir = Path.home() / ".docflow" / "profiles"
    if user_dir.exists():
        dirs.append(user_dir)
    return dirs


def _builtin_profile_path(name: str) -> Path | None:
    try:
        base = resources.files(BUILTIN_PACKAGE)
    except Exception:
        return None
    for ext in PROFILE_EXTS:
        candidate = base.joinpath(f"{name}{ext}")
        if candidate.is_file():
            return _as_path(candidate)
    return None


def _load_text_value(value: object, base_dir: Path) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        ref_path = Path(value)
        if not ref_path.is_absolute():
            ref_path = (base_dir / ref_path).resolve()
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8")
        return value
    raise ProfileError("Prompt/system_instruction must be a string or path")


def _load_schema_value(value: object, base_dir: Path) -> InternalSchema | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return parse_schema(value)
    if isinstance(value, str):
        schema_path = Path(value)
        if not schema_path.is_absolute():
            schema_path = (base_dir / schema_path).resolve()
        if not schema_path.exists():
            raise ProfileError(f"Schema path does not exist: {schema_path}")
        return parse_schema(load_structured(schema_path))
    raise ProfileError("Schema must be a mapping or a file path")


def _load_provider_options(obj: dict | None) -> ProviderOptions | None:
    if not obj:
        return None
    return ProviderOptions(
        model_name=obj.get("model") or obj.get("model_name"),
        temperature=obj.get("temperature"),
        max_output_tokens=obj.get("max_output_tokens"),
    )


def _load_profile_file(path: Path) -> ExtractionProfile:
    raw = load_structured(path)
    if not isinstance(raw, dict):
        raise ProfileError(f"Profile file must contain an object: {path}")

    name = raw.get("id") or raw.get("name") or path.stem
    mode = raw.get("mode") or raw.get("type") or "extract"
    multi = raw.get("multi_doc_behavior") or raw.get("multi") or "per_file"
    schema_val = raw.get("schema")
    provider_opts = raw.get("options") or raw.get("provider_options")

    schema_obj = _load_schema_value(schema_val, base_dir=path.parent)
    prompt_text = _load_text_value(raw.get("prompt"), base_dir=path.parent)
    system_text = _load_text_value(raw.get("system_instruction"), base_dir=path.parent)
    params_val = raw.get("params") if isinstance(raw.get("params"), dict) else None

    if mode not in {"extract", "describe", "classify"}:
        raise ProfileError(f"Unsupported profile mode '{mode}' in {path}")
    if multi not in {"per_file", "aggregate", "both"}:
        raise ProfileError(f"Unsupported multi-doc behavior '{multi}' in {path}")

    return ExtractionProfile(
        name=name,
        schema=schema_obj,
        mode=mode,
        multi_mode_default=multi,
        description=raw.get("description"),
        provider_options=_load_provider_options(provider_opts),
        prompt=prompt_text,
        system_instruction=system_text,
        params=params_val,
    )


def list_profiles(config: SdkConfig | None = None) -> List[str]:
    names = set()
    # project + user
    for directory in _profile_dirs(config):
        if directory.exists():
            for ext in PROFILE_EXTS:
                for path in directory.glob(f"*{ext}"):
                    names.add(path.stem)
    # built-ins
    try:
        base = resources.files(BUILTIN_PACKAGE)
        for ext in PROFILE_EXTS:
            for entry in base.glob(f"*{ext}"):
                names.add(_as_path(entry).stem)
    except Exception:
        pass
    return sorted(names)


def _find_profile_path(name: str, config: SdkConfig | None) -> Path | None:
    # Project-local → user-global → built-in
    for directory in _profile_dirs(config):
        for ext in PROFILE_EXTS:
            candidate = directory / f"{name}{ext}"
            if candidate.exists():
                return candidate
    builtin = _builtin_profile_path(name)
    if builtin:
        return builtin
    return None


def load_profile(name: str, config: SdkConfig | None = None) -> ExtractionProfile:
    path = _find_profile_path(name, config)
    if path is None:
        raise ProfileError(f"Profile '{name}' not found")
    return _load_profile_file(path)
