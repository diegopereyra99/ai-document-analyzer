from __future__ import annotations

"""Shared Profile Catalog for DocFlow and services.

Supports two backends:
- FS: local filesystem rooted profiles
- GCS: Google Cloud Storage bucket/prefix (optional dependency)

Profile layout:
  <prefix>/<profile_base>/<version>/
    prompt.txt
    system_instruction.txt
    schema.json
    [config.yaml]

When a caller omits the version segment, the latest version is resolved by
natural sort (v10 > v2 > v1). A resolved path always includes the version.
"""

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from google.cloud import storage  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    storage = None  # type: ignore

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None  # type: ignore


# --- Data types ---


@dataclass
class ProfileFileInfo:
    name: str
    size: int
    generation: Optional[int]
    updated: Optional[str]


@dataclass
class ProfileData:
    path: str  # resolved path including version
    prompt: str
    system_instruction: str
    schema: Dict[str, Any]
    config: Dict[str, Any]
    version: str
    files: List[ProfileFileInfo]
    available_versions: Optional[List[str]] = None


@dataclass
class ProfileMetadata:
    path: str
    version: str
    files: List[ProfileFileInfo]
    requested_path: Optional[str] = None
    available_versions: Optional[List[str]] = None


@dataclass
class CatalogConfig:
    backend: str  # "fs" | "gcs"
    # FS
    root_dir: Optional[Path] = None
    # GCS
    bucket: Optional[str] = None
    # Shared
    prefix: str = "profiles/"
    cache_ttl_seconds: int = 600

    def normalized_prefix(self) -> str:
        p = (self.prefix or "").strip("/")
        return f"{p}/" if p else ""


# --- Cache ---


class _CacheEntry:
    def __init__(self, profile: ProfileData, fetched_at: float):
        self.profile = profile
        self.fetched_at = fetched_at


_PROFILE_CACHE: Dict[str, _CacheEntry] = {}


# --- Helpers ---


def _normalize_path(path: str) -> str:
    return path.strip().strip("/")


_VERSION_RE = re.compile(r"v(\d+)$")


def _version_sort_key(version: str) -> Tuple[int, int | str]:
    m = _VERSION_RE.match(version)
    if m:
        return (0, int(m.group(1)))
    return (1, version)


# --- FS backend ---


def _fs_iter_schema_blobs(root: Path, prefix: str) -> Iterable[Path]:
    base = root / prefix
    if not base.exists():
        return []
    for p in base.rglob("schema.json"):
        yield p


def _fs_list_profiles(cfg: CatalogConfig, prefix_filter: Optional[str] = None) -> Tuple[List[str], Dict[str, List[str]]]:
    assert cfg.root_dir is not None
    filter_prefix = _normalize_path(prefix_filter or "")
    pref = cfg.normalized_prefix() + (f"{filter_prefix}/" if filter_prefix else "")
    root = cfg.root_dir
    bases: set[str] = set()
    versions_map: Dict[str, set[str]] = {}
    for schema_path in _fs_iter_schema_blobs(root, pref):
        rel = schema_path.relative_to(root).as_posix()
        if not rel.startswith(cfg.normalized_prefix()):
            continue
        without_prefix = rel[len(cfg.normalized_prefix()) :]
        parts = without_prefix.split("/")
        if len(parts) < 3:
            continue
        base = "/".join(parts[:-2])  # drop version + schema.json
        version = parts[-2]
        bases.add(base)
        versions_map.setdefault(base, set()).add(version)
    versions_sorted = {b: sorted(list(vs), key=_version_sort_key) for b, vs in versions_map.items()}
    return sorted(list(bases)), versions_sorted


def _fs_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fs_read_json(path: Path) -> Dict[str, Any]:
    text = _fs_read_text(path)
    return json.loads(text)


def _fs_read_yaml(path: Path) -> Dict[str, Any]:
    if yaml is None:
        return {}
    if not path.exists():
        return {}
    text = _fs_read_text(path)
    try:
        doc = yaml.safe_load(text) or {}
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _fs_build_version_hash(files: List[Path]) -> str:
    parts: List[str] = []
    for f in files:
        try:
            st = f.stat()
            mtime_ns = getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9))
            parts.append(f"{f.as_posix()}:{mtime_ns}:{st.st_size}")
        except Exception:
            parts.append(f"{f.as_posix()}:0:0")
    h = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return h[:16]


def _fs_load_profile(cfg: CatalogConfig, profile_path: str, collect_versions: bool) -> ProfileData:
    assert cfg.root_dir is not None
    resolved, available_versions = resolve_profile_path(profile_path, cfg, collect_versions=collect_versions)
    base = Path(cfg.normalized_prefix()) / Path(resolved)
    prompt_p = (cfg.root_dir / base / "prompt.txt").resolve()
    system_p = (cfg.root_dir / base / "system_instruction.txt").resolve()
    schema_p = (cfg.root_dir / base / "schema.json").resolve()
    config_p = (cfg.root_dir / base / "config.yaml").resolve()

    prompt = _fs_read_text(prompt_p)
    system = _fs_read_text(system_p)
    schema = _fs_read_json(schema_p)
    config = _fs_read_yaml(config_p)

    files: List[ProfileFileInfo] = []
    for name, path in (
        ("prompt.txt", prompt_p),
        ("system_instruction.txt", system_p),
        ("schema.json", schema_p),
    ):
        st = path.stat()
        files.append(
            ProfileFileInfo(
                name=name,
                size=st.st_size,
                generation=None,
                updated=datetime.fromtimestamp(st.st_mtime).isoformat(),
            )
        )
    if config_p.exists():
        st = config_p.stat()
        files.append(
            ProfileFileInfo(
                name="config.yaml",
                size=st.st_size,
                generation=None,
                updated=datetime.fromtimestamp(st.st_mtime).isoformat(),
            )
        )

    version = _fs_build_version_hash([prompt_p, system_p, schema_p])

    return ProfileData(
        path=resolved,
        prompt=prompt,
        system_instruction=system,
        schema=schema,
        config=config,
        version=version,
        files=files,
        available_versions=available_versions,
    )


# --- GCS backend ---


def _gcs_client():  # pragma: no cover - exercised in service environment
    if storage is None:
        raise RuntimeError("google-cloud-storage is required for GCS profile catalog")
    return storage.Client()


def _gcs_list_profiles(cfg: CatalogConfig, prefix_filter: Optional[str] = None) -> Tuple[List[str], Dict[str, List[str]]]:  # pragma: no cover
    client = _gcs_client()
    bucket = client.bucket(cfg.bucket)
    filter_prefix = _normalize_path(prefix_filter or "")
    pref = cfg.normalized_prefix() + (f"{filter_prefix}/" if filter_prefix else "")
    bases: set[str] = set()
    versions_map: Dict[str, set[str]] = {}
    for blob in client.list_blobs(bucket_or_name=bucket, prefix=pref):
        if blob.name.endswith("schema.json"):
            path_without_prefix = blob.name[len(cfg.normalized_prefix()) :].rstrip("/")
            profile_dir = path_without_prefix[: -len("schema.json")].rstrip("/")
            if not profile_dir:
                continue
            parts = profile_dir.split("/")
            if len(parts) < 2:
                continue
            base = "/".join(parts[:-1])
            version = parts[-1]
            bases.add(base)
            versions_map.setdefault(base, set()).add(version)
    versions_sorted: Dict[str, List[str]] = {
        base: sorted(list(vs), key=_version_sort_key) for base, vs in versions_map.items()
    }
    return sorted(bases), versions_sorted


def _gcs_download_text(bucket, path: str) -> Tuple[str, Any]:  # pragma: no cover
    blob = bucket.blob(path)
    text = blob.download_as_text(encoding="utf-8")
    return text, blob


def _gcs_download_json(bucket, path: str) -> Tuple[Dict[str, Any], Any]:  # pragma: no cover
    text, blob = _gcs_download_text(bucket, path)
    return json.loads(text), blob


def _gcs_download_yaml(bucket, path: str) -> Dict[str, Any]:  # pragma: no cover
    blob = bucket.blob(path)
    if not blob.exists():
        return {}
    text = blob.download_as_text(encoding="utf-8")
    if yaml is None:
        return {}
    try:
        doc = yaml.safe_load(text) or {}
        return doc if isinstance(doc, dict) else {}
    except Exception:
        return {}


def _gcs_build_version_hash(blobs: List[Any]) -> str:  # pragma: no cover
    parts = [f"{b.name}:{getattr(b, 'generation', None) or getattr(b, 'metageneration', 0) or 0}" for b in blobs]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _gcs_load_profile(cfg: CatalogConfig, profile_path: str, collect_versions: bool) -> ProfileData:  # pragma: no cover
    client = _gcs_client()
    bucket = client.bucket(cfg.bucket)
    resolved, available_versions = resolve_profile_path(profile_path, cfg, collect_versions=collect_versions)
    base = f"{cfg.normalized_prefix()}{resolved}/"

    prompt_txt, prompt_blob = _gcs_download_text(bucket, f"{base}prompt.txt")
    system_txt, system_blob = _gcs_download_text(bucket, f"{base}system_instruction.txt")
    schema_json, schema_blob = _gcs_download_json(bucket, f"{base}schema.json")
    config_yaml = _gcs_download_yaml(bucket, f"{base}config.yaml")

    files: List[ProfileFileInfo] = []
    for name, blob in (
        ("prompt.txt", prompt_blob),
        ("system_instruction.txt", system_blob),
        ("schema.json", schema_blob),
    ):
        files.append(
            ProfileFileInfo(
                name=name,
                size=blob.size or 0,
                generation=blob.generation,
                updated=blob.updated.isoformat() if getattr(blob, "updated", None) else None,
            )
        )
    cfg_blob = bucket.blob(f"{base}config.yaml")
    if cfg_blob.exists():
        files.append(
            ProfileFileInfo(
                name="config.yaml",
                size=cfg_blob.size or 0,
                generation=cfg_blob.generation,
                updated=cfg_blob.updated.isoformat() if getattr(cfg_blob, "updated", None) else None,
            )
        )

    version = _gcs_build_version_hash([prompt_blob, system_blob, schema_blob])

    return ProfileData(
        path=resolved,
        prompt=prompt_txt,
        system_instruction=system_txt,
        schema=schema_json,
        config=config_yaml,
        version=version,
        files=files,
        available_versions=available_versions,
    )


# --- Public API ---


def list_profiles(cfg: CatalogConfig, prefix_filter: Optional[str] = None) -> List[str]:
    bases, _ = list_profiles_with_versions(cfg, prefix_filter=prefix_filter)
    return bases


def list_profiles_with_versions(cfg: CatalogConfig, prefix_filter: Optional[str] = None) -> Tuple[List[str], Dict[str, List[str]]]:
    if cfg.backend == "fs":
        return _fs_list_profiles(cfg, prefix_filter=prefix_filter)
    if cfg.backend == "gcs":  # pragma: no cover
        return _gcs_list_profiles(cfg, prefix_filter=prefix_filter)
    raise ValueError("Unknown backend for profile catalog")


def list_profile_versions(base_path: str, cfg: CatalogConfig) -> List[str]:
    base_path = _normalize_path(base_path).rstrip("/")
    _, versions_map = list_profiles_with_versions(cfg)
    versions = versions_map.get(base_path, [])
    return sorted(list(versions), key=_version_sort_key)


def resolve_profile_path(profile_path: str, cfg: CatalogConfig, collect_versions: bool = False) -> Tuple[str, Optional[List[str]]]:
    normalized = _normalize_path(profile_path)
    # If it already points to concrete version, accept it if exists
    if cfg.backend == "fs":
        root = cfg.root_dir
        base = Path(cfg.normalized_prefix()) / normalized
        prompt_p = (root / base / "prompt.txt").resolve()
        system_p = (root / base / "system_instruction.txt").resolve()
        schema_p = (root / base / "schema.json").resolve()
        if prompt_p.exists() and system_p.exists() and schema_p.exists():
            versions = list_profile_versions("/".join(normalized.split("/")[:-1]), cfg) if collect_versions else None
            return normalized, versions
    else:  # gcs path existence check done via listing
        bases, versions_map = list_profiles_with_versions(cfg)  # pragma: no cover
        parts = normalized.split("/")
        if len(parts) >= 2:
            maybe_base = "/".join(parts[:-1])
            if maybe_base in bases and parts[-1] in set(versions_map.get(maybe_base, [])):
                versions = list_profile_versions(maybe_base, cfg) if collect_versions else None
                return normalized, versions

    # Not concrete version: choose latest
    parts = normalized.split("/")
    base = normalized
    if len(parts) >= 2:
        base = normalized
    versions = list_profile_versions(base, cfg)
    if not versions:
        raise FileNotFoundError(f"No versions found for profile path '{normalized}'")
    resolved = f"{normalized}/{versions[-1]}"
    all_versions = versions if collect_versions else None
    return resolved, all_versions


def load_profile(profile_path: str, cfg: CatalogConfig, bypass_cache: bool = False, collect_versions: bool = False) -> ProfileData:
    resolved, _ = resolve_profile_path(profile_path, cfg, collect_versions=False)
    cache_key = f"{cfg.backend}:{resolved}"
    now = time.time()
    entry = _PROFILE_CACHE.get(cache_key)
    if entry and not bypass_cache and (now - entry.fetched_at) < cfg.cache_ttl_seconds:
        return entry.profile

    if cfg.backend == "fs":
        prof = _fs_load_profile(cfg, resolved, collect_versions=collect_versions)
    elif cfg.backend == "gcs":  # pragma: no cover
        prof = _gcs_load_profile(cfg, resolved, collect_versions=collect_versions)
    else:
        raise ValueError("Unknown backend for profile catalog")

    _PROFILE_CACHE[cache_key] = _CacheEntry(profile=prof, fetched_at=now)
    return prof


def get_profile_metadata(profile_path: str, cfg: CatalogConfig) -> ProfileMetadata:
    prof = load_profile(profile_path, cfg, bypass_cache=True, collect_versions=True)
    return ProfileMetadata(
        path=prof.path,
        version=prof.version,
        files=prof.files,
        requested_path=_normalize_path(profile_path),
        available_versions=prof.available_versions,
    )

