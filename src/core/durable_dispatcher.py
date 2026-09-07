from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from src.core.durable_queue import DurableTaskQueue
from src.core.durable_workers import (
    ReviewResult,
    ReviewerAdapter,
    WorkRequest,
    WorkResult,
    WorkerAdapter,
    WorkerProfile,
    choose_worker,
)


@dataclass(frozen=True)
class DispatchOutcome:
    task_id: str
    worker_id: str
    checkpoint_sequence: int
    sent_to_review: bool
    result: WorkResult


class DurableDispatcher:
    """Runs one bounded durable work unit at a time.

    It deliberately does not loop forever. A scheduler can call dispatch_once
    repeatedly, while each invocation remains independently resumable.
    """

    def __init__(
        self,
        queue: DurableTaskQueue,
        workers: dict[str, WorkerAdapter],
        profiles: Iterable[WorkerProfile],
        reviewer: ReviewerAdapter | None = None,
        lease_seconds: int = 300,
    ) -> None:
        self.queue = queue
        self.workers = workers
        self.profiles = tuple(profiles)
        self.reviewer = reviewer
        self.lease_seconds = lease_seconds

    def dispatch_once(self, required_capabilities: set[str] | None = None) -> DispatchOutcome | None:
        required = required_capabilities or set()
        profile = choose_worker(required, self.profiles)
        if profile is None:
            return None
        worker = self.workers.get(profile.id)
        if worker is None:
            return None

        task = self.queue.claim_task(profile.id, lease_seconds=self.lease_seconds)
        if task is None:
            return None

        request = WorkRequest(
            task_id=task.id,
            objective=task.objective,
            checkpoint_sequence=task.checkpoint_sequence,
            checkpoint=dict(task.checkpoint),
            acceptance_criteria=tuple(task.acceptance_criteria),
            required_capabilities=frozenset(required),
        )
        result = worker.execute(request)
        sequence = self.queue.commit_checkpoint(
            task.id,
            profile.id,
            expected_sequence=task.checkpoint_sequence,
            checkpoint={
                "completed_step": result.completed_step,
                "next_step": result.next_step,
                "state": dict(result.checkpoint_state),
                "artifacts": list(result.artifacts),
                "notes": result.notes,
            },
        )

        sent_to_review = result.next_step is None
        if sent_to_review:
            self.queue.move_to_review(task.id, profile.id)

        return DispatchOutcome(
            task_id=task.id,
            worker_id=profile.id,
            checkpoint_sequence=sequence,
            sent_to_review=sent_to_review,
            result=result,
        )

    def review_once(self, task_id: str, result: WorkResult, worker_request: WorkRequest) -> ReviewResult | None:
        if self.reviewer is None:
            return None
        review = self.reviewer.review(worker_request, result)
        self.queue.complete_review(task_id, review.passed, review.feedback)
        return review
