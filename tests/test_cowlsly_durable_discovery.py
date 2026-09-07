import pytest

from src.core.durable_discovery import (
    ManifestError,
    RepositoryDescriptor,
    discover_enabled_projects,
    parse_manifest,
)


def test_repository_without_manifest_is_ignored():
    repos = [RepositoryDescriptor("Cowlsly/a", "main")]
    assert discover_enabled_projects(repos, {}) == ()


def test_enabled_manifest_is_discovered_across_non_main_default_branch():
    repos = [RepositoryDescriptor("Cowlsly/project", "root")]
    manifests = {
        "Cowlsly/project": {
            "version": 1,
            "enabled": True,
            "project_id": "project",
            "task_files": ["WORK/TASKS.json"],
            "instruction_files": ["AGENTS.md", "ROADMAP.md"],
            "status_file": ".cowlsly/status.md",
            "default_capabilities": ["coding", "research"],
        }
    }

    found = discover_enabled_projects(repos, manifests)

    assert len(found) == 1
    assert found[0].repository == "Cowlsly/project"
    assert found[0].task_files == ("WORK/TASKS.json",)
    assert found[0].default_capabilities == frozenset({"coding", "research"})


def test_disabled_manifest_is_not_discovered():
    repos = [RepositoryDescriptor("Cowlsly/project", "main")]
    manifests = {
        "Cowlsly/project": {
            "version": 1,
            "enabled": False,
            "project_id": "project",
        }
    }
    assert discover_enabled_projects(repos, manifests) == ()


def test_archived_repository_fails_closed():
    repo = RepositoryDescriptor("Cowlsly/old", "main", archived=True)
    with pytest.raises(ManifestError):
        parse_manifest(repo, {"version": 1, "enabled": True, "project_id": "old"})


def test_manifest_rejects_parent_directory_escape():
    repo = RepositoryDescriptor("Cowlsly/project", "main")
    with pytest.raises(ManifestError):
        parse_manifest(
            repo,
            {
                "version": 1,
                "enabled": True,
                "project_id": "project",
                "task_files": ["../secret.json"],
            },
        )


def test_manifest_rejects_unknown_version():
    repo = RepositoryDescriptor("Cowlsly/project", "main")
    with pytest.raises(ManifestError):
        parse_manifest(repo, {"version": 2, "enabled": True, "project_id": "project"})
