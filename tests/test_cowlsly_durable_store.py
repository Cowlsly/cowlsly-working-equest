import json

import pytest

from src.core.durable_bootstrap import BootstrappedProject
from src.core.durable_discovery import ProjectManifest
from src.core.durable_queue import DurableTask
from src.core.durable_store import ArtifactRegistration, PostgresDurableStore


class FakeCursor:
    def __init__(self, statements, artifact_id=17):
        self.statements = statements
        self.artifact_id = artifact_id
        self.closed = False

    def execute(self, query, params=()):
        normalized = " ".join(query.split())
        self.statements.append((normalized, params))

    def fetchone(self):
        return (self.artifact_id,)

    def close(self):
        self.closed = True


class FakeConnection:
    def __init__(self, *, fail_cursor=False):
        self.statements = []
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.fail_cursor = fail_cursor

    def cursor(self):
        if self.fail_cursor:
            raise RuntimeError("database unavailable")
        return FakeCursor(self.statements)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def project_manifest():
    return ProjectManifest(
        project_id="alpha",
        repository="Cowlsly/alpha",
        default_branch="main",
        task_files=("tasks.json",),
        instruction_files=(),
        status_file=None,
        default_capabilities=(),
    )


def test_persist_projects_upserts_definitions_and_dependencies_without_resetting_live_state():
    connection = FakeConnection()
    store = PostgresDurableStore(lambda: connection)
    task_a = DurableTask(
        id="TASK-A",
        project_id="alpha",
        objective="first",
        acceptance_criteria=["done"],
    )
    task_b = DurableTask(
        id="TASK-B",
        project_id="alpha",
        objective="second",
        acceptance_criteria=["done"],
        depends_on={"TASK-A"},
    )

    store.persist_projects((BootstrappedProject(project_manifest(), (task_a, task_b)),))

    assert connection.committed is True
    assert connection.rolled_back is False
    assert connection.closed is True

    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "ON CONFLICT (id) DO UPDATE" in sql
    task_upsert = next(
        statement
        for statement, _ in connection.statements
        if "INSERT INTO cowlsly_tasks" in statement
    )
    assert "status = EXCLUDED.status" not in task_upsert
    assert "checkpoint = EXCLUDED.checkpoint" not in task_upsert
    assert "attempts = EXCLUDED.attempts" not in task_upsert
    assert "leased_to" not in task_upsert
    assert any(
        params == ("TASK-B", "TASK-A")
        for statement, params in connection.statements
        if "INSERT INTO cowlsly_task_dependencies" in statement
    )


def test_register_artifact_persists_hash_metadata_and_event_in_one_transaction():
    connection = FakeConnection()
    store = PostgresDurableStore(lambda: connection)

    artifact_id = store.register_artifact(
        ArtifactRegistration(
            task_id="TASK-A",
            run_id=3,
            uri="github://Cowlsly/alpha/output.txt",
            sha256="abc123",
            metadata={"kind": "report"},
        )
    )

    assert artifact_id == 17
    assert connection.committed is True
    artifact_statement = next(
        item for item in connection.statements if "INSERT INTO cowlsly_artifacts" in item[0]
    )
    assert artifact_statement[1][:4] == (
        "TASK-A",
        3,
        "github://Cowlsly/alpha/output.txt",
        "abc123",
    )
    assert json.loads(artifact_statement[1][4]) == {"kind": "report"}
    event_statement = next(
        item for item in connection.statements if "artifact.registered" in item[0]
    )
    payload = json.loads(event_statement[1][2])
    assert payload["artifact_id"] == 17
    assert payload["sha256"] == "abc123"


def test_persistence_rolls_back_and_closes_on_failure():
    connection = FakeConnection(fail_cursor=True)
    store = PostgresDurableStore(lambda: connection)

    with pytest.raises(RuntimeError, match="database unavailable"):
        store.persist_projects(())

    assert connection.committed is False
    assert connection.rolled_back is True
    assert connection.closed is True
