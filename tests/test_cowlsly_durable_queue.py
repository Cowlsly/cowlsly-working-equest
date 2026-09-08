from datetime import datetime, timedelta, timezone
from threading import Thread

from src.core.durable_queue import DurableTask, DurableTaskQueue, LeaseLost, StaleCheckpoint


def test_two_workers_cannot_claim_same_task():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-1", project_id="p", objective="work", priority=90))
    claimed = []

    def worker(name: str) -> None:
        task = queue.claim_task(name)
        claimed.append(None if task is None else (name, task.id))

    threads = [Thread(target=worker, args=("marla",)), Thread(target=worker, args=("ussylia",))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    winners = [result for result in claimed if result is not None]
    assert len(winners) == 1
    assert winners[0][1] == "TASK-1"


def test_worker_b_resumes_from_worker_a_checkpoint_after_expiry():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-42", project_id="p", objective="resume me"))
    t0 = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)

    first = queue.claim_task("marla", lease_seconds=30, now=t0)
    assert first is not None
    assert queue.commit_checkpoint(
        "TASK-42",
        "marla",
        expected_sequence=0,
        checkpoint={"completed_step": "extract", "next_step": "classify"},
        now=t0 + timedelta(seconds=5),
    ) == 1

    recovered = queue.recover_expired_leases(now=t0 + timedelta(seconds=31))
    assert recovered == ["TASK-42"]

    second = queue.claim_task("ussylia", lease_seconds=30, now=t0 + timedelta(seconds=32))
    assert second is not None
    assert second.checkpoint_sequence == 1
    assert second.checkpoint["next_step"] == "classify"


def test_stale_worker_cannot_checkpoint_after_lease_loss():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-9", project_id="p", objective="guard ownership"))
    t0 = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    queue.claim_task("marla", lease_seconds=5, now=t0)

    try:
        queue.commit_checkpoint("TASK-9", "marla", 0, {}, now=t0 + timedelta(seconds=6))
    except LeaseLost:
        pass
    else:
        raise AssertionError("expired worker must not be allowed to checkpoint")


def test_optimistic_checkpoint_sequence_rejects_duplicate_commit():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-10", project_id="p", objective="sequence guard"))
    now = datetime(2026, 9, 8, 0, 0, tzinfo=timezone.utc)
    queue.claim_task("marla", lease_seconds=60, now=now)
    queue.commit_checkpoint("TASK-10", "marla", 0, {"next_step": "two"}, now=now)

    try:
        queue.commit_checkpoint("TASK-10", "marla", 0, {"next_step": "duplicate"}, now=now)
    except StaleCheckpoint:
        pass
    else:
        raise AssertionError("duplicate checkpoint sequence must be rejected")


def test_idempotency_key_can_only_be_registered_once():
    queue = DurableTaskQueue()
    assert queue.register_idempotency_key("TASK-10:1:1") is True
    assert queue.register_idempotency_key("TASK-10:1:1") is False


def test_dependencies_block_claim_until_done():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-A", project_id="p", objective="first", status="READY"))
    queue.add_task(DurableTask(id="TASK-B", project_id="p", objective="second", depends_on={"TASK-A"}, priority=100))

    claimed = queue.claim_task("marla")
    assert claimed is not None
    assert claimed.id == "TASK-A"
