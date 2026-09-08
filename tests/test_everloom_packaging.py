from pathlib import Path
import zipfile

from scripts.package_everloom import build, validate


def test_everloom_package_contains_skill_and_manifest(tmp_path: Path):
    output = build(tmp_path / "everloom.zip")
    validate(output)
    with zipfile.ZipFile(output) as archive:
        names = set(archive.namelist())
    assert "skills/everloom/SKILL.md" in names
    assert "EVERLOOM-MANIFEST.json" in names
    assert ".cowlsly/workflow.json" in names
    assert ".cowlsly/tasks/everloom-release.json" in names
    assert "migrations/002_cowlsly_queue_functions.sql" in names


def test_everloom_package_excludes_runtime_secrets_and_caches(tmp_path: Path):
    output = build(tmp_path / "everloom.zip")
    with zipfile.ZipFile(output) as archive:
        names = archive.namelist()
    assert all(".env" not in name for name in names)
    assert all("__pycache__" not in name for name in names)
    assert all(not name.endswith((".pyc", ".pyo")) for name in names)
