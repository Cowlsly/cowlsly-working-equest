from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from random import random
from typing import Iterable, Mapping


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 5
    base_seconds: float = 2.0
    max_seconds: float = 120.0
    jitter_ratio: float = 0.2

    def delay_seconds(self, attempt: int, *, jitter: bool = True) -> float:
        """Return bounded exponential backoff for a 1-based attempt number."""
        if attempt < 1:
            raise ValueError("attempt must be >= 1")
        raw = min(self.max_seconds, self.base_seconds * (2 ** (attempt - 1)))
        if not jitter or self.jitter_ratio <= 0:
            return raw
        spread = raw * self.jitter_ratio
        return max(0.0, raw - spread + (2 * spread * random()))


def find_dependency_cycle(graph: Mapping[str, Iterable[str]]) -> tuple[str, ...] | None:
    """Return one dependency cycle, including the repeated start node, or None."""
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> tuple[str, ...] | None:
        if node in visiting:
            start = stack.index(node)
            return tuple(stack[start:] + [node])
        if node in visited:
            return None

        visiting.add(node)
        stack.append(node)
        for dependency in graph.get(node, ()):  # unknown leaves are allowed
            cycle = visit(dependency)
            if cycle is not None:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in graph:
        cycle = visit(node)
        if cycle is not None:
            return cycle
    return None


def sha256_bytes(payload: bytes) -> str:
    return sha256(payload).hexdigest()


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with Path(path).open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()
