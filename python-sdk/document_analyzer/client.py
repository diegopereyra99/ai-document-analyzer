from __future__ import annotations

import base64
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Union

import requests

FileLike = Union[str, bytes, Path]


class DocumentAnalyzerError(Exception):
    pass


@dataclass
class Profile:
    name: str
    schema: Dict[str, Any]
    default_prompt: str = ""
    default_system_instruction: str = ""


_PROFILES: Dict[str, Profile] = {}


def register_profile(
    name: str,
    schema: Dict[str, Any],
    default_prompt: str = "",
    default_system_instruction: str = "",
) -> None:
    """Registra un perfil de extracción en memoria."""
    _PROFILES[name] = Profile(
        name=name,
        schema=schema,
        default_prompt=default_prompt,
        default_system_instruction=default_system_instruction,
    )


def get_profile(name: str) -> Profile:
    try:
        return _PROFILES[name]
    except KeyError:
        raise DocumentAnalyzerError(f"Profile '{name}' is not registered")


def _file_to_payload(file_ref: FileLike) -> Dict[str, Any]:
    """Convierte una referencia de archivo en el payload JSON esperado por el servicio."""
    if isinstance(file_ref, str):
        # URL remota
        if file_ref.startswith("http://") or file_ref.startswith("https://"):
            return {"url": file_ref}

        # Ruta local
        path = Path(file_ref)
        if not path.exists():
            raise DocumentAnalyzerError(f"File path does not exist: {file_ref}")
        data = path.read_bytes()
        mime, _ = mimetypes.guess_type(str(path))
        mime = mime or "application/octet-stream"
        return {
            "content": base64.b64encode(data).decode("ascii"),
            "mime_type": mime,
            "filename": path.name,
        }

    if isinstance(file_ref, Path):
        return _file_to_payload(str(file_ref))

    if isinstance(file_ref, (bytes, bytearray)):
        return {
            "content": base64.b64encode(bytes(file_ref)).decode("ascii"),
            "mime_type": "application/octet-stream",
        }

    raise TypeError(f"Unsupported file_ref type: {type(file_ref)}")


def _normalize_files(files: Iterable[FileLike]) -> List[Dict[str, Any]]:
    return [_file_to_payload(f) for f in files]


class DocumentAnalyzerClient:
    """Cliente para el servicio de análisis de documentos.

    El endpoint y la API key se pueden configurar vía parámetros o variables
    de entorno:

        DOCUMENT_ANALYZER_URL
        DOCUMENT_ANALYZER_API_KEY
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url or os.getenv("DOCUMENT_ANALYZER_URL")
        self.api_key = api_key or os.getenv("DOCUMENT_ANALYZER_API_KEY")
        self.timeout = timeout

        if not self.base_url:
            raise ValueError("DOCUMENT_ANALYZER_URL is not set and no base_url was provided")

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def extract(
        self,
        schema: Dict[str, Any],
        files: Iterable[FileLike],
        prompt: str = "",
        system_instruction: str = "",
        extra_params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload_files = _normalize_files(files)
        body: Dict[str, Any] = {
            "schema": schema,
            "files": payload_files,
            "prompt": prompt,
            "system_instruction": system_instruction,
        }
        if extra_params:
            body["extra_params"] = extra_params

        url = self.base_url.rstrip("/") + "/extract"

        try:
            resp = requests.post(
                url,
                headers=self._headers(),
                data=json.dumps(body),
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise DocumentAnalyzerError(f"Request error: {e}") from e

        if not resp.ok:
            raise DocumentAnalyzerError(
                f"Service returned {resp.status_code}: {resp.text[:500]}"
            )

        try:
            return resp.json()
        except json.JSONDecodeError as e:
            raise DocumentAnalyzerError(
                f"Failed to parse JSON response: {e}\nRaw: {resp.text[:500]}"
            ) from e


def extract_with_profile(
    client: DocumentAnalyzerClient,
    profile_name: str,
    files: Iterable[FileLike],
    prompt_override: Optional[str] = None,
    system_instruction_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Helper de alto nivel que usa un perfil registrado."""
    profile = get_profile(profile_name)
    prompt = prompt_override if prompt_override is not None else profile.default_prompt
    system_instruction = (
        system_instruction_override
        if system_instruction_override is not None
        else profile.default_system_instruction
    )
    return client.extract(
        schema=profile.schema,
        files=files,
        prompt=prompt,
        system_instruction=system_instruction,
    )
