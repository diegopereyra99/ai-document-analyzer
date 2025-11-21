import json
from pathlib import Path

import pytest

from docflow.sdk.config import SdkConfig
from docflow.sdk import profiles


def test_builtin_profiles_present():
    names = profiles.list_profiles()
    assert "extract" in names
    assert "describe" in names


def test_profile_resolution_project_first(tmp_path, monkeypatch):
    project_dir = tmp_path / "project"
    user_dir = tmp_path / "home"
    project_profiles = project_dir / ".docflow" / "profiles"
    user_profiles = user_dir / ".docflow" / "profiles"
    project_profiles.mkdir(parents=True)
    user_profiles.mkdir(parents=True)

    prof_data = {
        "name": "invoice_basic",
        "mode": "extract",
        "schema": {"type": "object", "properties": {"id": {"type": "string"}}},
    }
    (project_profiles / "invoice_basic.yaml").write_text(json.dumps(prof_data), encoding="utf-8")

    prof_data_user = {
        "name": "invoice_basic",
        "mode": "describe",
    }
    (user_profiles / "invoice_basic.yaml").write_text(json.dumps(prof_data_user), encoding="utf-8")

    monkeypatch.chdir(project_dir)
    monkeypatch.setattr(profiles.Path, "cwd", classmethod(lambda cls: project_dir))
    monkeypatch.setattr(profiles.Path, "home", classmethod(lambda cls: user_dir))

    cfg = SdkConfig()
    prof = profiles.load_profile("invoice_basic", cfg)
    assert prof.mode == "extract"  # project file used
