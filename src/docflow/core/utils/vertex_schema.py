"""Utilities for adapting JSON Schema to Vertex SDK-compatible response_schema.

Vertex's response_schema expects a constrained shape. This helper strips
unsupported keywords and coerces ambiguous forms to simple strings.
"""
from __future__ import annotations

from typing import Any, Dict


def normalize_for_vertex_schema(node: Any) -> Any:
    """Normalize a JSON-schema-like dict to a Vertex-compatible schema.

    - Remove unsupported keywords (e.g., additionalProperties when not an object mapping)
    - Coerce type lists to single string types (prefer non-null)
    - Ensure required is a list of strings if present
    - Recurse into properties/items/oneOf/anyOf/allOf
    """
    if isinstance(node, dict):
        # Strip known-problematic keys early
        node = dict(node)  # shallow copy
        node.pop("$schema", None)
        node.pop("$id", None)
        node.pop("title", None)
        node.pop("description", None)
        # additionalProperties with boolean True can trip the SDK; drop it
        if "additionalProperties" in node and not isinstance(node.get("additionalProperties"), dict):
            node.pop("additionalProperties", None)

        t = node.get("type")
        if isinstance(t, list):
            chosen: str | None = None
            for candidate in t:
                if isinstance(candidate, str):
                    chosen = candidate
                    if candidate.lower() != "null":
                        break
            if chosen is None and t:
                chosen = str(t[0])
            node["type"] = chosen

        # normalize required
        if "required" in node and not isinstance(node.get("required"), list):
            node.pop("required", None)

        for key, val in list(node.items()):
            if key in {"properties", "definitions"} and isinstance(val, dict):
                for sub_k, sub_v in list(val.items()):
                    val[sub_k] = normalize_for_vertex_schema(sub_v)
            elif key == "items":
                node[key] = normalize_for_vertex_schema(val)
            elif key in {"allOf", "anyOf", "oneOf"} and isinstance(val, list):
                node[key] = [normalize_for_vertex_schema(sub) for sub in val]
        return node
    if isinstance(node, list):
        return [normalize_for_vertex_schema(x) for x in node]
    return node

