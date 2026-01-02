import json
from pathlib import Path

from docflow.profile_catalog import (
    CatalogConfig,
    list_profiles,
    list_profiles_with_versions,
    list_profile_versions,
    resolve_profile_path,
    load_profile,
    get_profile_metadata,
)


def _write_profile(root: Path, base: str, version: str, schema: dict, prompt: str = "Prompt", system: str = "System", config: dict | None = None):
    dir_path = root / "profiles" / base / version
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "prompt.txt").write_text(prompt, encoding="utf-8")
    (dir_path / "system_instruction.txt").write_text(system, encoding="utf-8")
    (dir_path / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    if config is not None:
        import yaml

        (dir_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def test_fs_catalog_list_and_resolve(tmp_path: Path):
    # Create two versions
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    _write_profile(tmp_path, "invoices/extract", "v1", schema)
    _write_profile(tmp_path, "invoices/extract", "v2", schema)

    cfg = CatalogConfig(backend="fs", root_dir=tmp_path, prefix="profiles/")

    bases = list_profiles(cfg)
    assert "invoices/extract" in bases

    bases2, versions_map = list_profiles_with_versions(cfg)
    assert versions_map["invoices/extract"] == ["v1", "v2"]

    versions = list_profile_versions("invoices/extract", cfg)
    assert versions[-1] == "v2"

    resolved, all_versions = resolve_profile_path("invoices/extract", cfg, collect_versions=True)
    assert resolved.endswith("/v2")
    assert all_versions == ["v1", "v2"]


def test_fs_catalog_load_and_metadata(tmp_path: Path):
    schema = {"type": "object", "properties": {"id": {"type": "string"}}}
    _write_profile(tmp_path, "receipts/parse", "v1", schema, prompt="P", system="S", config={"generation_config": {"temperature": 0.1}})
    cfg = CatalogConfig(backend="fs", root_dir=tmp_path, prefix="profiles/")

    prof = load_profile("receipts/parse", cfg)
    assert prof.path.endswith("/v1")
    assert prof.prompt == "P"
    assert prof.system_instruction == "S"
    assert prof.schema["type"] == "object"
    assert isinstance(prof.version, str) and len(prof.version) == 16
    assert any(f.name == "config.yaml" for f in prof.files)

    meta = get_profile_metadata("receipts/parse", cfg)
    assert meta.path == prof.path
    assert meta.version == prof.version

