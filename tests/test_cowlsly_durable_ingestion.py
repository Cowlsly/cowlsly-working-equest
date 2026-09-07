import pytest

from src.core.durable_discovery import ProjectManifest
from src.core.durable_ingestion import TaskImportError, import_tasks


MANIFEST = ProjectManifest(
    repository="Cowlsly/project",
    project_id="project",
    enabled=True,
    task_files=("WORK/TASKS.json",),
    instruction_files=("AGENTS.md",),
    status_file=None,
    default_capabilities=frozenset({"coding"}),
)


def test_imports_tasks_with_defaults_and_dependencies():
    tasks = import_tasks(
        MANIFEST,
        {
            "tasks": [
                {
                    "id": "TASK-A",
                    "objective": "Build A",
                    "acceptance_criteria": ["A exists"],
                },
                {
                    "id": "TASK-B",
                    "objective": "Build B",
                    "priority": 90,
                    "depends_on": ["TASK-A"],
                    "acceptance_criteria": ["B tests pass"],
                },
            ]
        },
    )

    assert [task.id for task in tasks] == ["TASK-A", "TASK-B"]
    assert tasks[0].project_id == "project"
    assert tasks[0].status == "READY"
    assert tasks[1].status == "READY"
    assert tasks[1].depends_on == {"TASK-A"}
    assert tasks[1].priority == 90


def test_rejects_duplicate_task_ids():
    payload = {
        "tasks": [
            {"id": "TASK-A", "objective": "one", "acceptance_criteria": ["done"]},
            {"id": "TASK-A", "objective": "two", "acceptance_criteria": ["done"]},
        ]
    }
    with pytest.raises(TaskImportError, match="duplicate task IDs"):
        import_tasks(MANIFEST, payload)


def test_rejects_unknown_dependency():
    payload = {
        "tasks": [
            {
                "id": "TASK-A",
                "objective": "one",
                "depends_on": ["TASK-MISSING"],
                "acceptance_criteria": ["done"],
            }
        ]
    }
    with pytest.raises(TaskImportError, match="unknown tasks"):
        import_tasks(MANIFEST, payload)


def test_rejects_dependency_cycle():
    payload = {
        "tasks": [
            {"id": "TASK-A", "objective": "A", "depends_on": ["TASK-B"], "acceptance_criteria": ["done"]},
            {"id": "TASK-B", "objective": "B", "depends_on": ["TASK-A"], "acceptance_criteria": ["done"]},
        ]
    }
    with pytest.raises(TaskImportError, match="dependency cycle"):
        import_tasks(MANIFEST, payload)


def test_rejects_empty_acceptance_criteria():
    with pytest.raises(TaskImportError, match="acceptance_criteria"):
        import_tasks(MANIFEST, {"tasks": [{"id": "TASK-A", "objective": "A", "acceptance_criteria": []}]})
