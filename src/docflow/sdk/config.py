"""SDK configuration loader."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from .errors import ConfigError

try:  # Python 3.10 compatibility
    import tomllib  # type: ignore
except Exception:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass
class SdkConfig:
    mode: Literal["local", "remote"] = "local"
    endpoint_url: Optional[str] = None
    profile_dir: Optional[Path] = None
    default_output_format: str = "print"
    default_output_dir: Optional[Path] = None


DEFAULT_CONFIG_PATH = Path.home() / ".docflow" / "config.toml"


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    data = path.read_bytes()
    return tomllib.loads(data.decode("utf-8"))


def load_config(path: Path | None = None) -> SdkConfig:
    cfg = SdkConfig()
    cfg_path = path or DEFAULT_CONFIG_PATH
    file_data = _load_toml(cfg_path)
    docflow_section = file_data.get("docflow", file_data) if isinstance(file_data, dict) else {}

    env_mode = os.environ.get("DOCFLOW_MODE")
    env_endpoint = os.environ.get("DOCFLOW_ENDPOINT")
    env_profile_dir = os.environ.get("DOCFLOW_PROFILE_DIR")

    mode_val = env_mode or docflow_section.get("mode") or cfg.mode
    if mode_val not in {"local", "remote"}:
        raise ConfigError(f"Invalid DOCFLOW_MODE: {mode_val}")
    cfg.mode = mode_val

    cfg.endpoint_url = env_endpoint or docflow_section.get("endpoint") or docflow_section.get("endpoint_url")
    profile_dir_val = env_profile_dir or docflow_section.get("profile_dir")
    if profile_dir_val:
        cfg.profile_dir = Path(profile_dir_val).expanduser()

    cfg.default_output_format = docflow_section.get("default_output_format", cfg.default_output_format)
    out_dir_val = docflow_section.get("default_output_dir")
    if out_dir_val:
        cfg.default_output_dir = Path(out_dir_val).expanduser()

    return cfg


def merge_cli_overrides(config: SdkConfig, mode: str | None = None, endpoint: str | None = None) -> SdkConfig:
    updated = SdkConfig(
        mode=config.mode,
        endpoint_url=config.endpoint_url,
        profile_dir=config.profile_dir,
        default_output_format=config.default_output_format,
        default_output_dir=config.default_output_dir,
    )
    if mode:
        if mode not in {"local", "remote"}:
            raise ConfigError(f"Invalid mode: {mode}")
        updated.mode = mode
    if endpoint:
        updated.endpoint_url = endpoint
    return updated
