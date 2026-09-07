from __future__ import annotations

from typing import Any

from src.core.durable_discovery import ProjectManifest
from src.core.durable_policy import find_dependency_cycle
from src.core.durable_queue import DurableTask


class TaskImportError(ValueError):
    pass


def import_tasks(manifest: ProjectManifest, payload: dict[str, Any]) -> tuple[DurableTask, ...]:
    raw_tasks = payload.get("tasks")
    if not isinstance(raw_tasks, list):
        raise TaskImportError("task payload must contain a tasks list")

    tasks = tuple(_parse_task(manifest, raw) for raw in raw_tasks)
    ids = [task.id for task in tasks]
    if len(ids) != len(set(ids)):
        raise TaskImportError("duplicate task IDs in import payload")

    known_ids = set(ids)
    for task in tasks:
        missing = set(task.depends_on) - known_ids
        if missing:
            raise TaskImportError(f"{task.id} depends on unknown tasks: {sorted(missing)}")

    dependency_map = {task.id: set(task.depends_on) for task in tasks}
    cycle = find_dependency_cycle(dependency_map)
    if cycle:
        raise TaskImportError("dependency cycle detected: " + " -> ".join(cycle))

    return tasks


def _parse_task(manifest: ProjectManifest, raw: Any) -> DurableTask:
    if not isinstance(raw, dict):
        raise TaskImportError("each task must be an object")

    task_id = raw.get("id")
    if not isinstance(task_id, str) or not task_id.startswith("TASK-"):
        raise TaskImportError("task id must start with TASK-")

    objective = raw.get("objective")
    if not isinstance(objective, str) or not objective.strip():
        raise TaskImportError(f"{task_id}: objective must be non-empty")

    priority = raw.get("priority", 50)
    if not isinstance(priority, int) or isinstance(priority, bool) or not 0 <= priority <= 100:
        raise TaskImportError(f"{task_id}: priority must be an integer from 0 to 100")

    acceptance = raw.get("acceptance_criteria")
    if not isinstance(acceptance, list) or not acceptance or not all(
        isinstance(item, str) and item.strip() for item in acceptance
    ):
        raise TaskImportError(f"{task_id}: acceptance_criteria must contain at least one string")

    dependencies = raw.get("depends_on", [])
    if not isinstance(dependencies, list) or not all(isinstance(item, str) for item in dependencies):
        raise TaskImportError(f"{task_id}: depends_on must be a list of task IDs")
    if task_id in dependencies:
        raise TaskImportError(f"{task_id}: task cannot depend on itself")

    max_attempts = raw.get("max_attempts", 5)
    if not isinstance(max_attempts, int) or isinstance(max_attempts, bool) or max_attempts < 1:
        raise TaskImportError(f"{task_id}: max_attempts must be >= 1")

    # Dependency readiness is evaluated by the queue at claim time. Tasks stay
    # READY here so they automatically become claimable once their dependencies
    # reach DONE, without requiring a second state-transition daemon.
    return DurableTask(
        id=task_id,
        project_id=manifest.project_id,
        objective=objective.strip(),
        priority=priority,
        status="READY",
        acceptance_criteria=[item.strip() for item in acceptance],
        depends_on=set(dependencies),
        max_attempts=max_attempts,
    )
