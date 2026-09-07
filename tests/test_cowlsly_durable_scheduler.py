from src.core.durable_scheduler import DurableScheduler


class FakeDispatcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def dispatch_once(self, required_capabilities=None):
        self.calls += 1
        if not self.outcomes:
            return None
        return self.outcomes.pop(0)


def test_scheduler_stops_when_queue_is_empty():
    dispatcher = FakeDispatcher(["one", "two"])
    scheduler = DurableScheduler(dispatcher, max_dispatches_per_tick=10)

    tick = scheduler.tick()

    assert tick.dispatched == ("one", "two")
    assert tick.stopped_reason == "queue-empty-or-no-worker"
    assert dispatcher.calls == 3


def test_scheduler_obeys_dispatch_limit():
    dispatcher = FakeDispatcher(["one", "two", "three"])
    scheduler = DurableScheduler(dispatcher, max_dispatches_per_tick=2)

    tick = scheduler.tick()

    assert tick.dispatched == ("one", "two")
    assert tick.stopped_reason == "dispatch-limit"
    assert dispatcher.calls == 2


def test_scheduler_honours_stop_request_before_dispatch():
    dispatcher = FakeDispatcher(["one"])
    scheduler = DurableScheduler(dispatcher, should_stop=lambda: True)

    tick = scheduler.tick()

    assert tick.dispatched == ()
    assert tick.stopped_reason == "stop-requested"
    assert dispatcher.calls == 0
