"""Profile resolution for SDK and CLI (single store + built-ins fallback)."""
from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import List, Optional

from docflow.core.errors import ProfileError
from docflow.core.models.profiles import ExtractionProfile
from docflow.core.models.schema_defs import parse_schema
from docflow.core.providers.base import ProviderOptions
from docflow.core.utils.io import load_structured
from docflow.profile_catalog import (
    CatalogConfig,
    list_profiles as catalog_list_profiles,
    list_profiles_with_versions as catalog_list_profiles_with_versions,
)
from docflow.profile_catalog import load_profile as catalog_load_profile
from docflow.sdk.config import SdkConfig
from docflow.sdk.config import load_config

PROFILE_EXTS = [".yaml", ".yml", ".json"]
BUILTIN_PACKAGE = "docflow.sdk.builtin_profiles"


def _default_store_dir(config: SdkConfig | None) -> Path:
    if config and config.profile_dir:
        return config.profile_dir
    # default to user-level store to keep a deterministic single location
    return Path.home() / ".docflow" / "profiles"


def _catalog_config(config: SdkConfig | None = None) -> CatalogConfig | None:
    cfg = config or load_config()
    root_dir = _default_store_dir(cfg)
    if not root_dir:
        return None
    return CatalogConfig(backend="fs", root_dir=root_dir, prefix="profiles/")


def list_profiles(config: SdkConfig | None = None) -> List[str]:
    cfg = _catalog_config(config)
    names = set()
    if cfg and cfg.root_dir and cfg.root_dir.exists():
        try:
            names.update(catalog_list_profiles(cfg))
        except Exception:
            pass
    builtin_cfg = _builtin_catalog_config()
    if builtin_cfg and builtin_cfg.root_dir and builtin_cfg.root_dir.exists():
        try:
            names.update(catalog_list_profiles(builtin_cfg))
        except Exception:
            pass
    # built-ins as fallback
    try:
        base = resources.files(BUILTIN_PACKAGE)
        for ext in PROFILE_EXTS:
            for entry in base.glob(f"*{ext}"):
                names.add(entry.stem)
    except Exception:
        pass
    return sorted(names)


def list_profiles_with_versions(config: SdkConfig | None = None, prefix: str | None = None) -> tuple[list[str], dict[str, list[str]]]:
    bases: set[str] = set()
    versions_map: dict[str, set[str]] = {}

    def _merge(b: list[str], vm: dict[str, list[str]]):
        for base in b:
            bases.add(base)
        for k, v in vm.items():
            versions_map.setdefault(k, set()).update(v)

    cfg = _catalog_config(config)
    if cfg and cfg.root_dir and cfg.root_dir.exists():
        try:
            b, vm = catalog_list_profiles_with_versions(cfg, prefix_filter=prefix)
            _merge(b, vm)
        except Exception:
            pass

    builtin_cfg = _builtin_catalog_config()
    if builtin_cfg and builtin_cfg.root_dir and builtin_cfg.root_dir.exists():
        try:
            b, vm = catalog_list_profiles_with_versions(builtin_cfg, prefix_filter=prefix)
            _merge(b, vm)
        except Exception:
            pass

    return sorted(bases), {k: sorted(list(v)) for k, v in versions_map.items()}


def _load_from_catalog(name: str, config: SdkConfig | None) -> ExtractionProfile | None:
    cfg = _catalog_config(config)
    if cfg is None:
        return None
    try:
        prof = catalog_load_profile(name, cfg)
    except FileNotFoundError:
        return None
    except Exception as exc:
        raise ProfileError(str(exc)) from exc

    cfg_dict = prof.config if isinstance(prof.config, dict) else {}
    opts = cfg_dict.get("generation_config") if isinstance(cfg_dict, dict) else None
    mode_val = cfg_dict.get("mode") or "extract"
    multi_val = cfg_dict.get("multi_doc_behavior") or cfg_dict.get("multi") or "per_file"
    provider_opts = None
    if isinstance(opts, dict):
        provider_opts = ProviderOptions(
            model_name=opts.get("model") or opts.get("model_name"),
            temperature=opts.get("temperature"),
            top_p=opts.get("top_p"),
            max_output_tokens=opts.get("max_output_tokens"),
        )

    return ExtractionProfile(
        name=prof.path,
        schema=parse_schema(prof.schema),
        mode=mode_val,
        multi_mode_default=multi_val,
        description=cfg_dict.get("description") if isinstance(cfg_dict, dict) else None,
        provider_options=provider_opts,
        prompt=prof.prompt,
        system_instruction=prof.system_instruction,
        params=None,
    )


def _builtin_catalog_config() -> CatalogConfig | None:
    try:
        base = resources.files(BUILTIN_PACKAGE)
    except Exception:
        return None
    try:
        with resources.as_file(base) as path:
            root = (path / "profiles").resolve()
            if root.exists():
                return CatalogConfig(backend="fs", root_dir=root, prefix="")
    except Exception:
        return None
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


def _load_schema_value(value: object, base_dir: Path):
    if value is None:
        return None
    if isinstance(value, dict):
        return parse_schema(value)
    if isinstance(value, str):
        schema_path = Path(value)
        if not schema_path.is_absolute():
            schema_path = (base_dir / schema_path).resolve()
        return parse_schema(load_structured(schema_path))
    raise ProfileError("Schema must be a mapping or a file path")


def _load_builtin(name: str) -> ExtractionProfile | None:
    # First try catalog-style built-ins
    cfg = _builtin_catalog_config()
    if cfg:
        try:
            prof = catalog_load_profile(name, cfg)
            cfg_dict = prof.config if isinstance(prof.config, dict) else {}
            opts = cfg_dict.get("generation_config") if isinstance(cfg_dict, dict) else None
            mode_val = cfg_dict.get("mode") or "extract"
            multi_val = cfg_dict.get("multi_doc_behavior") or cfg_dict.get("multi") or "per_file"
            provider_opts = None
            if isinstance(opts, dict):
                provider_opts = ProviderOptions(
                    model_name=opts.get("model") or opts.get("model_name"),
                    temperature=opts.get("temperature"),
                    top_p=opts.get("top_p"),
                    max_output_tokens=opts.get("max_output_tokens"),
                )
            return ExtractionProfile(
                name=prof.path,
                schema=parse_schema(prof.schema),
                mode=mode_val,
                multi_mode_default=multi_val,
                description=cfg_dict.get("description") if isinstance(cfg_dict, dict) else None,
                provider_options=provider_opts,
                prompt=prof.prompt,
                system_instruction=prof.system_instruction,
                params=None,
            )
        except FileNotFoundError:
            pass
        except Exception as exc:
            raise ProfileError(str(exc)) from exc

    # Legacy packaged YAML/JSON files
    try:
        base = resources.files(BUILTIN_PACKAGE)
    except Exception:
        return None
    target = None
    for ext in PROFILE_EXTS:
        candidate = base.joinpath(f"{name}{ext}")
        if candidate.is_file():
            target = candidate
            break
    if target is None:
        return None

    with resources.as_file(target) as path:
        doc = load_structured(path)
        if not isinstance(doc, dict):
            raise ProfileError(f"Invalid built-in profile format for '{name}'")

    base_dir = path.parent
    schema_obj = _load_schema_value(doc.get("schema"), base_dir) if doc.get("schema") is not None else None
    prompt_text = _load_text_value(doc.get("prompt"), base_dir)
    system_text = _load_text_value(doc.get("system_instruction"), base_dir)

    opts = doc.get("options") or doc.get("provider_options") or {}
    provider_opts = ProviderOptions(
        model_name=opts.get("model") or opts.get("model_name"),
        temperature=opts.get("temperature"),
        max_output_tokens=opts.get("max_output_tokens"),
    )

    return ExtractionProfile(
        name=doc.get("id") or doc.get("name") or name,
        schema=schema_obj,
        mode=doc.get("mode") or "extract",
        multi_mode_default=doc.get("multi_doc_behavior") or doc.get("multi") or "per_file",
        description=doc.get("description"),
        provider_options=provider_opts,
        prompt=prompt_text,
        system_instruction=system_text,
        params=doc.get("params") if isinstance(doc.get("params"), dict) else None,
    )


def load_profile(name: str, config: SdkConfig | None = None) -> ExtractionProfile:
    # Single store (fs catalog) first
    prof = _load_from_catalog(name, config)
    if prof:
        return prof
    # Built-ins fallback
    prof = _load_builtin(name)
    if prof:
        return prof
    raise ProfileError(f"Profile '{name}' not found")
