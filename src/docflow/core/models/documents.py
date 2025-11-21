"""Document sources and loaders."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from ..errors import DocumentError


@runtime_checkable
class DocSource(Protocol):
    def load(self) -> bytes | str:
        ...

    def display_name(self) -> str:
        ...


@dataclass
class FileSource:
    path: Path

    def load(self) -> bytes:
        try:
            return self.path.read_bytes()
        except FileNotFoundError as exc:  # pragma: no cover - exercised indirectly
            raise DocumentError(f"File not found: {self.path}") from exc
        except Exception as exc:  # pragma: no cover
            raise DocumentError(f"Failed to read file {self.path}: {exc}") from exc

    def display_name(self) -> str:
        return self.path.name


@dataclass
class GcsSource:
    uri: str  # gs://bucket/path

    def load(self) -> bytes:
        try:
            from google.cloud import storage  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise DocumentError(
                "google-cloud-storage is required to load GCS URIs"
            ) from exc

        try:
            parsed = self.uri.replace("gs://", "", 1)
            bucket_name, blob_path = parsed.split("/", 1)
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            return blob.download_as_bytes()
        except ValueError as exc:  # pragma: no cover
            raise DocumentError(f"Invalid GCS URI: {self.uri}") from exc
        except Exception as exc:  # pragma: no cover
            raise DocumentError(f"Failed to download {self.uri}: {exc}") from exc

    def display_name(self) -> str:
        return self.uri


@dataclass
class RawTextSource:
    text: str
    name: str = "inline"

    def load(self) -> str:
        return self.text

    def display_name(self) -> str:
        return self.name


def load_content(source: DocSource) -> bytes | str:
    try:
        data = source.load()
    except DocumentError:
        raise
    except Exception as exc:  # pragma: no cover
        raise DocumentError(f"Failed to load {source}: {exc}") from exc

    if not isinstance(data, (bytes, str)):
        raise DocumentError("Document loader must return bytes or string")
    return data
