"""Python client for DocFlow."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

import requests

from docflow.core.extraction.engine import ExtractionResult, MultiResult, extract
from docflow.core.models import FileSource
from docflow.core.models.schema_defs import InternalSchema, parse_schema
from docflow.core.providers.base import ModelProvider, ProviderOptions
from docflow.core.providers.gemini import GeminiProvider
from docflow.sdk.errors import ConfigError, RemoteServiceError
from docflow.sdk.profiles import load_profile
from .config import SdkConfig, load_config, merge_cli_overrides


class DocflowClient:
    def __init__(
        self,
        mode: str | None = None,
        endpoint_url: str | None = None,
        provider: ModelProvider | None = None,
        config: SdkConfig | None = None,
    ) -> None:
        base_config = config or load_config()
        self.config = merge_cli_overrides(base_config, mode=mode, endpoint=endpoint_url)
        self.mode = self.config.mode
        self.endpoint_url = self.config.endpoint_url or endpoint_url
        self.provider = provider

        if self.mode == "remote" and not self.endpoint_url:
            raise ConfigError("Remote mode requires endpoint_url")

    # --- public methods ---
    def extract(self, schema: dict | InternalSchema, files: List[str | Path], multi_mode: str = "per_file"):
        profile = load_profile("extract", self.config)
        return self._execute(schema, files, profile_name=None, profile=profile, multi_mode=multi_mode)

    def extract_all(self, files: List[str | Path], multi_mode: str = "per_file"):
        profile = load_profile("extract_all", self.config)
        return self._execute(schema=None, files=files, profile_name="extract_all", profile=profile, multi_mode=multi_mode)

    def describe(self, files: List[str | Path], multi_mode: str = "per_file"):
        profile = load_profile("describe", self.config)
        return self._execute(schema=None, files=files, profile_name="describe", profile=profile, multi_mode=multi_mode)

    def run_profile(self, profile_name: str, files: List[str | Path], multi_mode: str = "per_file"):
        profile = load_profile(profile_name, self.config)
        return self._execute(schema=profile.schema, files=files, profile_name=profile_name, profile=profile, multi_mode=multi_mode)

    # --- internal helpers ---
    def _sources_from_files(self, files: Iterable[str | Path]) -> List[FileSource]:
        return [FileSource(Path(path)) for path in files]

    def _provider(self) -> ModelProvider:
        if self.provider:
            return self.provider
        return GeminiProvider()

    def _execute(
        self,
        schema: dict | InternalSchema | None,
        files: List[str | Path],
        profile_name: str | None,
        profile,
        multi_mode: str,
    ):
        if self.mode == "local":
            sources = self._sources_from_files(files)
            internal_schema = schema
            if isinstance(schema, dict):
                internal_schema = parse_schema(schema)
            return extract(
                docs=sources,
                schema=internal_schema,
                profile=profile,
                provider=self._provider(),
                multi_mode=multi_mode,
            )
        return self._execute_remote(schema=schema, files=files, profile_name=profile_name, multi_mode=multi_mode)

    def _execute_remote(
        self,
        schema: dict | InternalSchema | None,
        files: List[str | Path],
        profile_name: str | None,
        multi_mode: str,
    ):
        payload = {
            "schema": schema if isinstance(schema, dict) else None,
            "files": [{"uri": str(Path(f))} for f in files],
            "profile": profile_name,
            "options": {},
            "multi": multi_mode,
        }
        url = f"{self.endpoint_url.rstrip('/')}/extract-data"
        resp = requests.post(url, json=payload, timeout=60)
        try:
            data = resp.json()
        except Exception as exc:  # pragma: no cover
            raise RemoteServiceError(f"Invalid response from service: {exc}") from exc

        if not resp.ok or (isinstance(data, dict) and data.get("ok") is False):
            message = data.get("error") if isinstance(data, dict) else resp.text
            raise RemoteServiceError(f"Service error: {message}")

        if not isinstance(data, dict):
            raise RemoteServiceError("Unexpected service response")

        payload_data = data.get("data", {})
        meta = data.get("meta", {})

        if isinstance(payload_data, list):
            results: List[ExtractionResult] = []
            for item in payload_data:
                body = item if isinstance(item, dict) else {"value": item}
                results.append(ExtractionResult(body, meta))
            return results
        body = payload_data if isinstance(payload_data, dict) else {"value": payload_data}
        return ExtractionResult(body, meta)
