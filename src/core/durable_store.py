from __future__ import annotations

import json
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from src.core.durable_bootstrap import BootstrappedProject
from src.core.durable_queue import DurableTask


class Cursor(Protocol):
    def execute(self, query: str, params: tuple[Any, ...] = ()) -> Any: ...
    def fetchone(self) -> Any: ...
    def close(self) -> None: ...


class Connection(Protocol):
    def cursor(self) -> Cursor: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
    def close(self) -> None: ...


ConnectionFactory = Callable[[], Connection]


@dataclass(frozen=True)
class ArtifactRegistration:
    task_id: str
    uri: str
    sha256: str | None = None
    metadata: dict[str, Any] | None = None
    run_id: int | None = None


class PostgresDurableStore:
    """Small DB-API persistence bridge for the durable workflow schema.

    The adapter intentionally does not import psycopg directly. Production can
    pass ``lambda: psycopg.connect(dsn)`` while unit tests use a fake DB-API
    connection. Re-importing a project updates task definition fields but never
    resets live execution state such as status, checkpoint, attempts, or leases.
    """

    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self._connection_factory = connection_factory

    def persist_projects(self, projects: tuple[BootstrappedProject, ...]) -> None:
        connection = self._connection_factory()
        try:
            with closing(connection.cursor()) as cursor:
                for project in projects:
                    self._upsert_project(cursor, project.manifest.project_id, project.manifest.repository)
                    for task in project.tasks:
                        self._upsert_task(cursor, task)

                # Dependencies are replaced only after every task has been
                # upserted, allowing cross-file dependency references safely.
                for project in projects:
                    for task in project.tasks:
                        self._replace_dependencies(cursor, task)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def register_artifact(self, artifact: ArtifactRegistration) -> int:
        connection = self._connection_factory()
        try:
            with closing(connection.cursor()) as cursor:
                cursor.execute(
                    """
                    INSERT INTO cowlsly_artifacts(task_id, run_id, uri, sha256, metadata)
                    VALUES (%s, %s, %s, %s, %s::jsonb)
                    RETURNING id
                    """,
                    (
                        artifact.task_id,
                        artifact.run_id,
                        artifact.uri,
                        artifact.sha256,
                        json.dumps(artifact.metadata or {}, sort_keys=True),
                    ),
                )
                row = cursor.fetchone()
                if not row:
                    raise RuntimeError("artifact insert did not return an id")
                artifact_id = int(row[0])
                cursor.execute(
                    """
                    INSERT INTO cowlsly_events(task_id, run_id, event_type, payload)
                    VALUES (%s, %s, 'artifact.registered', %s::jsonb)
                    """,
                    (
                        artifact.task_id,
                        artifact.run_id,
                        json.dumps(
                            {
                                "artifact_id": artifact_id,
                                "uri": artifact.uri,
                                "sha256": artifact.sha256,
                            },
                            sort_keys=True,
                        ),
                    ),
                )
            connection.commit()
            return artifact_id
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _upsert_project(cursor: Cursor, project_id: str, repository: str) -> None:
        cursor.execute(
            """
            INSERT INTO cowlsly_projects(id, repository, enabled)
            VALUES (%s, %s, true)
            ON CONFLICT (id) DO UPDATE
            SET repository = EXCLUDED.repository,
                enabled = true
            """,
            (project_id, repository),
        )

    @staticmethod
    def _upsert_task(cursor: Cursor, task: DurableTask) -> None:
        checkpoint = dict(task.checkpoint)
        checkpoint["sequence"] = task.checkpoint_sequence
        cursor.execute(
            """
            INSERT INTO cowlsly_tasks(
                id, project_id, objective, status, priority,
                acceptance_criteria, checkpoint, attempts, max_attempts
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET project_id = EXCLUDED.project_id,
                objective = EXCLUDED.objective,
                priority = EXCLUDED.priority,
                acceptance_criteria = EXCLUDED.acceptance_criteria,
                max_attempts = EXCLUDED.max_attempts,
                updated_at = now()
            """,
            (
                task.id,
                task.project_id,
                task.objective,
                task.status,
                task.priority,
                json.dumps(task.acceptance_criteria),
                json.dumps(checkpoint, sort_keys=True),
                task.attempts,
                task.max_attempts,
            ),
        )
        cursor.execute(
            """
            INSERT INTO cowlsly_events(task_id, event_type, payload)
            VALUES (%s, 'task.definition_synced', %s::jsonb)
            """,
            (
                task.id,
                json.dumps({"project_id": task.project_id}, sort_keys=True),
            ),
        )

    @staticmethod
    def _replace_dependencies(cursor: Cursor, task: DurableTask) -> None:
        cursor.execute(
            "DELETE FROM cowlsly_task_dependencies WHERE task_id = %s",
            (task.id,),
        )
        for dependency in sorted(task.depends_on):
            cursor.execute(
                """
                INSERT INTO cowlsly_task_dependencies(task_id, depends_on_task_id)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (task.id, dependency),
            )
