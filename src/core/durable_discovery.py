from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable


MANIFEST_PATH = ".cowlsly/workflow.json"


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class RepositoryDescriptor:
    full_name: str
    default_branch: str
    archived: bool = False


@dataclass(frozen=True)
class ProjectManifest:
    repository: str
    project_id: str
    enabled: bool
    task_files: tuple[str, ...]
    instruction_files: tuple[str, ...]
    status_file: str | None
    default_capabilities: frozenset[str]


def parse_manifest(repository: RepositoryDescriptor, payload: dict[str, Any]) -> ProjectManifest:
    if repository.archived:
        raise ManifestError("archived repositories cannot be enabled")

    version = payload.get("version")
    if version != 1:
        raise ManifestError("manifest version must be 1")

    enabled = payload.get("enabled")
    if not isinstance(enabled, bool):
        raise ManifestError("enabled must be a boolean")

    project_id = payload.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        raise ManifestError("project_id must be a non-empty string")

    task_files = _path_list(payload.get("task_files", []), "task_files")
    instruction_files = _path_list(payload.get("instruction_files", []), "instruction_files")

    status_file = payload.get("status_file")
    if status_file is not None:
        status_file = _path(status_file, "status_file")

    capabilities = payload.get("default_capabilities", [])
    if not isinstance(capabilities, list) or not all(isinstance(item, str) and item.strip() for item in capabilities):
        raise ManifestError("default_capabilities must be a list of non-empty strings")

    return ProjectManifest(
        repository=repository.full_name,
        project_id=project_id.strip(),
        enabled=enabled,
        task_files=task_files,
        instruction_files=instruction_files,
        status_file=status_file,
        default_capabilities=frozenset(item.strip() for item in capabilities),
    )


def discover_enabled_projects(
    repositories: Iterable[RepositoryDescriptor],
    manifests: dict[str, dict[str, Any] | None],
) -> tuple[ProjectManifest, ...]:
    """Return only repositories that explicitly opt in with a valid manifest.

    Repositories without a manifest are ignored. Invalid manifests fail closed
    for that repository and should be reported by the connector layer.
    """

    discovered: list[ProjectManifest] = []
    for repository in repositories:
        payload = manifests.get(repository.full_name)
        if payload is None:
            continue
        manifest = parse_manifest(repository, payload)
        if manifest.enabled:
            discovered.append(manifest)
    return tuple(sorted(discovered, key=lambda item: (item.project_id, item.repository)))


def _path_list(value: Any, field: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ManifestError(f"{field} must be a list")
    return tuple(_path(item, field) for item in value)


def _path(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{field} must contain non-empty repository-relative paths")
    path = value.strip().replace("\\", "/")
    if path.startswith("/") or path.startswith("../") or "/../" in path or path == "..":
        raise ManifestError(f"{field} contains an unsafe path: {value}")
    return path
