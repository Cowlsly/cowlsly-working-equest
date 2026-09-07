from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DurableTask:
    id: str
    project_id: str
    objective: str
    priority: int = 50
    status: str = "READY"
    acceptance_criteria: list[str] = field(default_factory=list)
    depends_on: set[str] = field(default_factory=set)
    checkpoint_sequence: int = 0
    checkpoint: dict[str, Any] = field(default_factory=dict)
    attempts: int = 0
    max_attempts: int = 5
    leased_to: str | None = None
    lease_until: datetime | None = None
    heartbeat_at: datetime | None = None


@dataclass(frozen=True)
class QueueEvent:
    task_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime


class LeaseLost(RuntimeError):
    pass


class StaleCheckpoint(RuntimeError):
    pass


class DurableTaskQueue:
    """Reference queue semantics used by tests and local development.

    Production PostgreSQL uses the same rules with row locks and SKIP LOCKED.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, DurableTask] = {}
        self._events: list[QueueEvent] = []
        self._idempotency_keys: set[str] = set()
        self._lock = Lock()

    def add_task(self, task: DurableTask) -> None:
        with self._lock:
            if task.id in self._tasks:
                raise ValueError(f"duplicate task: {task.id}")
            self._tasks[task.id] = task
            self._event(task.id, "task.created", {"status": task.status})

    def get_task(self, task_id: str) -> DurableTask:
        return self._tasks[task_id]

    def events(self, task_id: str | None = None) -> list[QueueEvent]:
        if task_id is None:
            return list(self._events)
        return [event for event in self._events if event.task_id == task_id]

    def claim_task(self, worker_id: str, lease_seconds: int = 300, *, now: datetime | None = None) -> DurableTask | None:
        now = now or utcnow()
        with self._lock:
            candidates = [
                task
                for task in self._tasks.values()
                if task.status == "READY"
                and task.attempts < task.max_attempts
                and all(self._tasks[dependency].status == "DONE" for dependency in task.depends_on)
            ]
            if not candidates:
                return None
            task = sorted(candidates, key=lambda item: (-item.priority, item.id))[0]
            task.status = "RUNNING"
            task.leased_to = worker_id
            task.heartbeat_at = now
            task.lease_until = now + timedelta(seconds=lease_seconds)
            task.attempts += 1
            self._event(task.id, "task.claimed", {"worker_id": worker_id, "attempt": task.attempts})
            return task

    def heartbeat(self, task_id: str, worker_id: str, lease_seconds: int = 300, *, now: datetime | None = None) -> None:
        now = now or utcnow()
        with self._lock:
            task = self._require_active_lease(task_id, worker_id, now)
            task.heartbeat_at = now
            task.lease_until = now + timedelta(seconds=lease_seconds)
            self._event(task.id, "task.heartbeat", {"worker_id": worker_id})

    def commit_checkpoint(
        self,
        task_id: str,
        worker_id: str,
        expected_sequence: int,
        checkpoint: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> int:
        now = now or utcnow()
        with self._lock:
            task = self._require_active_lease(task_id, worker_id, now)
            if task.checkpoint_sequence != expected_sequence:
                raise StaleCheckpoint(
                    f"expected checkpoint {expected_sequence}, found {task.checkpoint_sequence}"
                )
            task.checkpoint_sequence += 1
            task.checkpoint = dict(checkpoint)
            self._event(
                task.id,
                "task.checkpoint",
                {"sequence": task.checkpoint_sequence, "worker_id": worker_id},
            )
            return task.checkpoint_sequence

    def register_idempotency_key(self, key: str) -> bool:
        with self._lock:
            if key in self._idempotency_keys:
                return False
            self._idempotency_keys.add(key)
            return True

    def move_to_review(self, task_id: str, worker_id: str, *, now: datetime | None = None) -> None:
        now = now or utcnow()
        with self._lock:
            task = self._require_active_lease(task_id, worker_id, now)
            task.status = "REVIEW"
            task.leased_to = None
            task.lease_until = None
            self._event(task.id, "task.review_requested", {"worker_id": worker_id})

    def complete_review(self, task_id: str, passed: bool, feedback: str | None = None) -> None:
        with self._lock:
            task = self._tasks[task_id]
            if task.status != "REVIEW":
                raise ValueError("task is not in REVIEW")
            task.status = "DONE" if passed else "READY"
            self._event(task.id, "task.review_passed" if passed else "task.review_failed", {"feedback": feedback})

    def recover_expired_leases(self, *, now: datetime | None = None) -> list[str]:
        now = now or utcnow()
        recovered: list[str] = []
        with self._lock:
            for task in self._tasks.values():
                if task.status == "RUNNING" and task.lease_until is not None and task.lease_until <= now:
                    task.status = "READY" if task.attempts < task.max_attempts else "FAILED"
                    old_worker = task.leased_to
                    task.leased_to = None
                    task.lease_until = None
                    recovered.append(task.id)
                    self._event(task.id, "task.lease_expired", {"worker_id": old_worker, "new_status": task.status})
        return recovered

    def _require_active_lease(self, task_id: str, worker_id: str, now: datetime) -> DurableTask:
        task = self._tasks[task_id]
        if task.status != "RUNNING" or task.leased_to != worker_id or task.lease_until is None or task.lease_until <= now:
            raise LeaseLost(f"worker {worker_id} no longer owns an active lease for {task_id}")
        return task

    def _event(self, task_id: str, event_type: str, payload: dict[str, Any]) -> None:
        self._events.append(QueueEvent(task_id, event_type, payload, utcnow()))
