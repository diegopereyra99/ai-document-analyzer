"""Schema representations and minimal validation."""
from __future__ import annotations

from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List

from .. import config
from ..errors import SchemaError

ALLOWED_TYPES = {"string", "number", "integer", "boolean", "object", "array"}


def _normalize_type(value: str | None) -> str:
    if not value:
        return "string"
    return str(value).lower()


@dataclass
class Field:
    name: str
    type: str = "string"
    required: bool = False
    description: str | None = None

    def __post_init__(self) -> None:
        self.type = _normalize_type(self.type)
        if self.type not in ALLOWED_TYPES:
            # Lenient: accept unknown types but keep them as-is
            self.type = str(self.type)


@dataclass
class RecordSet:
    name: str
    fields: List[Field] = dataclass_field(default_factory=list)


@dataclass
class InternalSchema:
    global_fields: List[Field] = dataclass_field(default_factory=list)
    record_sets: List[RecordSet] = dataclass_field(default_factory=list)


# --- Parsing helpers ---

def _parse_fields_from_properties(props: Dict[str, Any], required_list: List[str] | None = None) -> List[Field]:
    required_set = set(required_list or [])
    fields: List[Field] = []
    for name, spec in props.items():
        if not isinstance(spec, dict):
            continue
        fields.append(
            Field(
                name=name,
                type=spec.get("type") or "string",
                required=name in required_set or bool(spec.get("required")),
                description=spec.get("description"),
            )
        )
    return fields


def _parse_fields_from_list(items: List[Dict[str, Any]]) -> List[Field]:
    fields: List[Field] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        fields.append(
            Field(
                name=name,
                type=entry.get("type") or "string",
                required=bool(entry.get("required")),
                description=entry.get("description"),
            )
        )
    return fields


def _is_array_type(t: Any) -> bool:
    if isinstance(t, str):
        return t.lower() == "array"
    if isinstance(t, list):
        return any(isinstance(x, str) and x.lower() == "array" for x in t)
    return False


def _json_schema_to_internal(raw: Dict[str, Any]) -> InternalSchema:
    # Top-level array: treat items as a record set named "items" (or title if provided)
    if _is_array_type(raw.get("type")):
        items = raw.get("items") or {}
        if not isinstance(items, dict):
            raise SchemaError("Array schema requires an 'items' object")
        rs_fields = _parse_fields_from_properties(items.get("properties", {}) or {}, items.get("required"))
        rs_name = raw.get("title") or "items"
        return InternalSchema(global_fields=[], record_sets=[RecordSet(name=rs_name, fields=rs_fields)])

    # Expect a JSON-schema-like object shape
    if raw.get("type") not in (None, "object", "OBJECT", "Object") and "properties" not in raw:
        raise SchemaError("Top-level schema must be an object")
    properties = raw.get("properties") or {}
    required_list = raw.get("required") or []
    global_fields = _parse_fields_from_properties(properties, required_list)

    record_sets: List[RecordSet] = []
    # Allow a custom record_sets section
    raw_record_sets = raw.get("record_sets") or raw.get("records") or []
    if isinstance(raw_record_sets, list):
        for rs in raw_record_sets:
            if not isinstance(rs, dict) or not isinstance(rs.get("name"), str):
                continue
            rs_props = rs.get("properties") or {}
            rs_required = rs.get("required") or []
            rs_fields = []
            if isinstance(rs_props, dict):
                rs_fields = _parse_fields_from_properties(rs_props, rs_required)
            elif isinstance(rs.get("fields"), list):
                rs_fields = _parse_fields_from_list(rs["fields"])
            record_sets.append(RecordSet(name=rs["name"], fields=rs_fields))

    # Allow shorthand: a "records" property that is an array of objects
    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        if prop.get("type") in ("array", "ARRAY") and isinstance(prop.get("items"), dict):
            items = prop["items"]
            if isinstance(items.get("properties"), dict):
                rs_fields = _parse_fields_from_properties(items.get("properties"), items.get("required"))
                record_sets.append(RecordSet(name=name, fields=rs_fields))

    return InternalSchema(global_fields=global_fields, record_sets=record_sets)


def parse_schema(raw: Dict[str, Any]) -> InternalSchema:
    """Parse a lenient JSON-Schema-like dict into :class:`InternalSchema`."""
    if not isinstance(raw, dict):
        raise SchemaError("Schema must be a dictionary")

    # Prefer explicit internal format
    global_fields: List[Field] = []
    record_sets: List[RecordSet] = []

    if isinstance(raw.get("global_fields"), list):
        global_fields = _parse_fields_from_list(raw["global_fields"])
    if isinstance(raw.get("record_sets"), list):
        for rs in raw["record_sets"]:
            if not isinstance(rs, dict) or not isinstance(rs.get("name"), str):
                continue
            rs_fields: List[Field] = []
            if isinstance(rs.get("fields"), list):
                rs_fields = _parse_fields_from_list(rs["fields"])
            elif isinstance(rs.get("properties"), dict):
                rs_fields = _parse_fields_from_properties(rs["properties"], rs.get("required"))
            record_sets.append(RecordSet(name=rs["name"], fields=rs_fields))

    # If nothing parsed yet, fall back to JSON schema style
    if not global_fields and not record_sets:
        return _json_schema_to_internal(raw)

    return InternalSchema(global_fields=global_fields, record_sets=record_sets)


# --- Validation helpers ---

def _is_type_match(expected: str, value: Any) -> bool:
    if value is None:
        return True
    if expected == "string":
        return isinstance(value, str)
    if expected == "number":
        return isinstance(value, (int, float))
    if expected == "integer":
        return isinstance(value, int)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    # Unknown types: accept
    return True


def _ensure_dict_data(schema: InternalSchema, data: Dict[str, Any] | list[Any]) -> Dict[str, Any]:
    """Allow top-level list when schema is a single record set."""
    if isinstance(data, dict):
        return data
    if isinstance(data, list) and schema.record_sets and not schema.global_fields and len(schema.record_sets) == 1:
        return {schema.record_sets[0].name: data}
    raise SchemaError("Provider output must be a dictionary")


def validate_output(schema: InternalSchema, data: Dict[str, Any] | list[Any]) -> None:
    """Minimal sanity checks for provider output.

    Raises :class:`SchemaError` if required fields are missing or types are grossly incompatible.
    """
    data = _ensure_dict_data(schema, data)

    for field in schema.global_fields:
        if field.required and field.name not in data:
            raise SchemaError(f"Missing required field '{field.name}'")
        if field.name in data and not _is_type_match(field.type, data[field.name]):
            raise SchemaError(f"Field '{field.name}' expected type {field.type}")

    for record_set in schema.record_sets:
        value = data.get(record_set.name)
        if value is None:
            continue
        if not isinstance(value, list):
            raise SchemaError(f"Record set '{record_set.name}' must be a list")
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                raise SchemaError(f"Record {idx} in '{record_set.name}' must be an object")
            for f in record_set.fields:
                if f.required and f.name not in item:
                    raise SchemaError(f"Missing required field '{f.name}' in record {idx} of '{record_set.name}'")
                if f.name in item and not _is_type_match(f.type, item[f.name]):
                    raise SchemaError(
                        f"Field '{f.name}' in record set '{record_set.name}' expected type {f.type}"
                    )


# --- Normalization ---

def _coerce_type(expected: str, value: Any) -> Any:
    if value is None:
        return None
    try:
        if expected == "string":
            return str(value)
        if expected == "number":
            return float(value)
        if expected == "integer":
            return int(value)
        if expected == "boolean":
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().lower() in {"true", "1", "yes", "y"}
            return bool(value)
    except Exception:
        return value
    return value


def normalize_output(schema: InternalSchema, data: Dict[str, Any] | list[Any]) -> Dict[str, Any]:
    """Normalize provider output and preserve unknown fields under ``extra``."""
    if isinstance(data, list) and schema.record_sets and not schema.global_fields and len(schema.record_sets) == 1:
        data = {schema.record_sets[0].name: data}
    if not isinstance(data, dict):
        return {"data": data, "extra": {}}

    normalized: Dict[str, Any] = {}
    top_extra: Dict[str, Any] = {}

    # Global fields
    for field in schema.global_fields:
        if field.name in data:
            normalized[field.name] = _coerce_type(field.type, data[field.name])
        else:
            normalized[field.name] = None if field.required else None

    # Record sets
    for record_set in schema.record_sets:
        records_raw = data.get(record_set.name, [])
        if not isinstance(records_raw, list):
            records_raw = []
        normalized_records: List[Dict[str, Any]] = []
        for record in records_raw:
            if not isinstance(record, dict):
                continue
            rec_out: Dict[str, Any] = {}
            rec_extra: Dict[str, Any] = {}
            for field in record_set.fields:
                if field.name in record:
                    rec_out[field.name] = _coerce_type(field.type, record[field.name])
                else:
                    rec_out[field.name] = None if field.required else None
            for key, val in record.items():
                if key not in rec_out:
                    rec_extra[key] = val
            if rec_extra:
                rec_out["extra"] = rec_extra
            normalized_records.append(rec_out)
        normalized[record_set.name] = normalized_records

    # Catch-all extras
    known_keys = set(normalized.keys()) | {f.name for f in schema.global_fields} | {rs.name for rs in schema.record_sets}
    for key, val in data.items():
        if key not in known_keys:
            top_extra[key] = val
    if top_extra:
        normalized["extra"] = top_extra

    return normalized
