from src.core.durable_policy import RetryPolicy, find_dependency_cycle, sha256_bytes


def test_retry_policy_is_bounded_and_exponential_without_jitter():
    policy = RetryPolicy(base_seconds=2.0, max_seconds=10.0, jitter_ratio=0)
    assert [policy.delay_seconds(i, jitter=False) for i in range(1, 6)] == [2.0, 4.0, 8.0, 10.0, 10.0]


def test_retry_policy_rejects_zero_attempt():
    policy = RetryPolicy()
    try:
        policy.delay_seconds(0)
    except ValueError:
        pass
    else:
        raise AssertionError("attempt zero must be rejected")


def test_dependency_cycle_detected():
    graph = {"A": ["B"], "B": ["C"], "C": ["A"]}
    cycle = find_dependency_cycle(graph)
    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle[:-1]) == {"A", "B", "C"}


def test_acyclic_dependency_graph_returns_none():
    assert find_dependency_cycle({"A": ["B"], "B": ["C"], "C": []}) is None


def test_sha256_bytes_is_stable():
    assert sha256_bytes(b"cowlsly") == sha256_bytes(b"cowlsly")
    assert sha256_bytes(b"cowlsly") != sha256_bytes(b"Cowlsly")
