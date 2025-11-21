from docflow.core.extraction.engine import extract
from docflow.core.models.documents import RawTextSource
from docflow.core.models.schema_defs import parse_schema


class FakeProvider:
    def __init__(self, payload: dict):
        self.payload = payload
        self.last_usage = {"input_tokens": 1, "output_tokens": 1}
        self.last_model = "fake-model"

    def generate_structured(self, prompt: str, schema, options=None, system_instruction=None, attachments=None):
        return self.payload


def test_extract_per_file():
    schema = parse_schema({"type": "object", "properties": {"name": {"type": "string"}}})
    provider = FakeProvider({"name": "Test"})
    result = extract([RawTextSource("hello", name="doc1")], schema=schema, provider=provider)
    assert isinstance(result, list)
    assert result[0].data["name"] == "Test"
    assert result[0].meta["docs"] == ["doc1"]


def test_extract_aggregate():
    schema = parse_schema({"type": "object", "properties": {"count": {"type": "integer"}}})
    provider = FakeProvider({"count": 2})
    result = extract([RawTextSource("a1"), RawTextSource("a2")], schema=schema, provider=provider, multi_mode="aggregate")
    assert result.data["count"] == 2
