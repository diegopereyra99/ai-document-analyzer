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
