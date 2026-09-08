from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class WorkRequest:
    task_id: str
    objective: str
    checkpoint_sequence: int
    checkpoint: dict[str, Any]
    acceptance_criteria: tuple[str, ...]
    repository: str | None = None
    required_capabilities: frozenset[str] = frozenset()


@dataclass(frozen=True)
class WorkResult:
    completed_step: str | None
    next_step: str | None
    checkpoint_state: dict[str, Any] = field(default_factory=dict)
    artifacts: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class ReviewResult:
    passed: bool
    criteria: dict[str, bool]
    feedback: str = ""


class WorkerAdapter(Protocol):
    worker_id: str

    def execute(self, request: WorkRequest) -> WorkResult:
        """Execute exactly one bounded logical unit and return resumable state."""
        ...


class ReviewerAdapter(Protocol):
    reviewer_id: str

    def review(self, request: WorkRequest, result: WorkResult) -> ReviewResult:
        """Evaluate explicit acceptance criteria rather than worker self-report."""
        ...


@dataclass(frozen=True)
class WorkerProfile:
    id: str
    provider: str
    capabilities: frozenset[str]
    enabled: bool = True
    priority: int = 50
    cost_tier: int = 2


DEFAULT_WORKERS: tuple[WorkerProfile, ...] = (
    WorkerProfile(
        id="marla",
        provider="openai",
        capabilities=frozenset({"coding", "reasoning", "research", "review", "tool-use"}),
        priority=100,
        cost_tier=3,
    ),
    WorkerProfile(
        id="ussylia",
        provider="configured-agent",
        capabilities=frozenset({"research", "creative", "review", "tool-use"}),
        priority=90,
        cost_tier=2,
    ),
    WorkerProfile(
        id="meta",
        provider="meta",
        capabilities=frozenset({"research", "drafting", "classification", "creative"}),
        enabled=False,
        priority=70,
        cost_tier=2,
    ),
    WorkerProfile(
        id="gemini",
        provider="google",
        capabilities=frozenset({"research", "multimodal", "drafting", "classification"}),
        enabled=False,
        priority=70,
        cost_tier=2,
    ),
    WorkerProfile(
        id="claude",
        provider="anthropic",
        capabilities=frozenset({"coding", "reasoning", "drafting", "review"}),
        enabled=False,
        priority=70,
        cost_tier=3,
    ),
)


def choose_worker(
    required_capabilities: set[str] | frozenset[str],
    profiles: tuple[WorkerProfile, ...] = DEFAULT_WORKERS,
) -> WorkerProfile | None:
    required = frozenset(required_capabilities)
    eligible = [
        profile
        for profile in profiles
        if profile.enabled and required.issubset(profile.capabilities)
    ]
    if not eligible:
        return None
    return sorted(eligible, key=lambda p: (-p.priority, p.cost_tier, p.id))[0]
