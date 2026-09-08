from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.core.durable_dispatcher import DispatchOutcome, DurableDispatcher


@dataclass(frozen=True)
class SchedulerTick:
    started_at: datetime
    dispatched: tuple[DispatchOutcome, ...]
    stopped_reason: str


class DurableScheduler:
    """Bounded scheduler for durable work.

    One tick performs a finite amount of work and returns. An external cron,
    service loop, or DeterminFlow automation can call tick repeatedly. This
    avoids making scheduler lifetime part of task correctness.
    """

    def __init__(
        self,
        dispatcher: DurableDispatcher,
        max_dispatches_per_tick: int = 10,
        should_stop: Callable[[], bool] | None = None,
    ) -> None:
        if max_dispatches_per_tick < 1:
            raise ValueError("max_dispatches_per_tick must be >= 1")
        self.dispatcher = dispatcher
        self.max_dispatches_per_tick = max_dispatches_per_tick
        self.should_stop = should_stop or (lambda: False)

    def tick(self, required_capabilities: set[str] | None = None) -> SchedulerTick:
        started_at = datetime.now(timezone.utc)
        outcomes: list[DispatchOutcome] = []

        for _ in range(self.max_dispatches_per_tick):
            if self.should_stop():
                return SchedulerTick(started_at, tuple(outcomes), "stop-requested")

            outcome = self.dispatcher.dispatch_once(required_capabilities)
            if outcome is None:
                return SchedulerTick(started_at, tuple(outcomes), "queue-empty-or-no-worker")
            outcomes.append(outcome)

        return SchedulerTick(started_at, tuple(outcomes), "dispatch-limit")
