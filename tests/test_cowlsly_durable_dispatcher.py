from src.core.durable_dispatcher import DurableDispatcher
from src.core.durable_queue import DurableTask, DurableTaskQueue
from src.core.durable_workers import ReviewResult, WorkResult, WorkerProfile


class StubWorker:
    worker_id = "marla"

    def execute(self, request):
        return WorkResult(
            completed_step="inspect",
            next_step=None,
            checkpoint_state={"seen": request.task_id},
            artifacts=("artifact://result",),
            notes="bounded unit complete",
        )


class StubReviewer:
    reviewer_id = "reviewer"

    def review(self, request, result):
        return ReviewResult(passed=True, criteria={"artifact exists": True})


def test_dispatch_once_claims_executes_checkpoints_and_moves_to_review():
    queue = DurableTaskQueue()
    queue.add_task(
        DurableTask(
            id="TASK-DISPATCH",
            project_id="p",
            objective="do one bounded unit",
            acceptance_criteria=["artifact exists"],
        )
    )
    profile = WorkerProfile(
        id="marla",
        provider="openai",
        capabilities=frozenset({"coding"}),
        enabled=True,
        priority=100,
    )
    dispatcher = DurableDispatcher(queue, {"marla": StubWorker()}, [profile], reviewer=StubReviewer())

    outcome = dispatcher.dispatch_once({"coding"})

    assert outcome is not None
    assert outcome.task_id == "TASK-DISPATCH"
    assert outcome.worker_id == "marla"
    assert outcome.checkpoint_sequence == 1
    assert outcome.sent_to_review is True
    task = queue.get_task("TASK-DISPATCH")
    assert task.status == "REVIEW"
    assert task.checkpoint["state"]["seen"] == "TASK-DISPATCH"


def test_dispatcher_refuses_worker_without_required_capability():
    queue = DurableTaskQueue()
    queue.add_task(DurableTask(id="TASK-NOPE", project_id="p", objective="needs vision"))
    profile = WorkerProfile(
        id="marla",
        provider="openai",
        capabilities=frozenset({"coding"}),
        enabled=True,
    )
    dispatcher = DurableDispatcher(queue, {"marla": StubWorker()}, [profile])

    assert dispatcher.dispatch_once({"multimodal"}) is None
    assert queue.get_task("TASK-NOPE").status == "READY"
