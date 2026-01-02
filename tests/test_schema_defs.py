import pytest

from docflow.core.errors import SchemaError
from docflow.core.models.schema_defs import normalize_output, parse_schema, validate_output


def test_parse_schema_properties():
    raw = {
        "type": "object",
        "properties": {
            "invoice_id": {"type": "string"},
            "total": {"type": "number"},
        },
        "required": ["invoice_id"],
    }
    schema = parse_schema(raw)
    assert [f.name for f in schema.global_fields] == ["invoice_id", "total"]
    assert schema.global_fields[0].required is True


def test_validate_output_required():
    schema = parse_schema({"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
    with pytest.raises(SchemaError):
        validate_output(schema, {})


def test_normalize_output_preserves_extra():
    schema = parse_schema({"type": "object", "properties": {"name": {"type": "string"}}})
    result = normalize_output(schema, {"name": "Alice", "other": 5})
    assert result["name"] == "Alice"
    assert "extra" in result and result["extra"]["other"] == 5


def test_array_schema_top_level_list_output():
    raw = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name"],
        },
    }
    schema = parse_schema(raw)
    assert len(schema.record_sets) == 1
    assert schema.record_sets[0].name == "items"
    # Validate a top-level list output
    validate_output(schema, [{"name": "Bob", "age": 30}])
    normalized = normalize_output(schema, [{"name": "Bob", "age": 30}])
    assert normalized["items"][0]["name"] == "Bob"
