"""IO helpers."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml


def load_structured(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    data = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(data) or {}
    return json.loads(data)


def save_json(path: str | Path, payload: Dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
