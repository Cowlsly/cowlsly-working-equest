from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.core.durable_discovery import ProjectManifest, RepositoryDescriptor, discover_enabled_projects
from src.core.durable_ingestion import import_tasks
from src.core.durable_queue import DurableTask


class ProjectSource(Protocol):
    def list_repositories(self) -> tuple[RepositoryDescriptor, ...]: ...
    def collect_manifests(
        self, repositories: tuple[RepositoryDescriptor, ...]
    ) -> dict[str, dict | None]: ...
    def fetch_json_file(self, repository: RepositoryDescriptor, path: str) -> dict: ...


@dataclass(frozen=True)
class BootstrappedProject:
    manifest: ProjectManifest
    tasks: tuple[DurableTask, ...]


class ProjectSink(Protocol):
    def persist_projects(self, projects: tuple[BootstrappedProject, ...]) -> None: ...


def bootstrap_projects(source: ProjectSource) -> tuple[BootstrappedProject, ...]:
    repositories = source.list_repositories()
    manifests = source.collect_manifests(repositories)
    enabled = discover_enabled_projects(repositories, manifests)
    repo_by_name = {repository.full_name: repository for repository in repositories}

    bootstrapped: list[BootstrappedProject] = []
    for manifest in enabled:
        repository = repo_by_name[manifest.repository]
        combined_tasks: list[dict] = []
        for path in manifest.task_files:
            payload = source.fetch_json_file(repository, path)
            tasks = payload.get("tasks")
            if not isinstance(tasks, list):
                raise ValueError(f"{manifest.repository}:{path} must contain a tasks list")
            combined_tasks.extend(tasks)

        imported = import_tasks(manifest, {"tasks": combined_tasks}) if combined_tasks else ()
        bootstrapped.append(BootstrappedProject(manifest=manifest, tasks=imported))

    return tuple(bootstrapped)


def bootstrap_and_persist(
    source: ProjectSource,
    sink: ProjectSink,
) -> tuple[BootstrappedProject, ...]:
    """Discover, validate, and transactionally hand projects to persistence.

    Returning the immutable bootstrap result keeps this entry point useful for
    logging and dry-run summaries while the sink owns all database mutation.
    """

    projects = bootstrap_projects(source)
    sink.persist_projects(projects)
    return projects
