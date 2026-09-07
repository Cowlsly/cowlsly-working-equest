# Cowlsly Durable Workflow Core

## Principle

**Do not make the agent immortal. Make the work resumable.**

This layer extends DeterminFlow with a persistent cross-project work queue for Marla, Ussylia and other workers. GitHub remains the durable project record; a database holds live execution state; workers are replaceable.

## State machine

`BLOCKED -> READY -> LEASED -> RUNNING -> REVIEW -> DONE`

Failure paths:

- transient failure: `RUNNING -> READY` after retry/backoff
- worker disappears: lease expires, task returns to `READY`
- review fails: `REVIEW -> READY` with reviewer feedback
- unrecoverable failure: `RUNNING -> FAILED`, requiring explicit intervention

Only acceptance criteria may move a task to DONE.

## Task contract

Every task must define:

- stable task ID
- project/repository
- objective
- priority
- dependencies
- acceptance criteria
- current checkpoint
- attempt count and retry limit
- lease owner and expiry when claimed
- artifact/result references
- timestamps

## Worker protocol

1. Query for the highest-priority READY task whose dependencies are DONE.
2. Atomically acquire a time-limited lease.
3. Load only the task contract, required project instructions and relevant artifacts.
4. Execute one bounded logical unit.
5. Validate output.
6. Persist artifacts and an event.
7. Advance the checkpoint.
8. Renew the lease while actively working.
9. When acceptance criteria are satisfied, move to REVIEW.
10. Reviewer either marks DONE or returns actionable feedback and requeues the task.

Workers must never rely on chat history as the only record of progress.

## Persistence

Initial database tables:

- `projects`
- `tasks`
- `task_runs`
- `events`
- `artifacts`
- `agents`

GitHub stores project instructions, source changes, human-readable task material and durable artifacts. The database stores queue state, leases, checkpoints and execution events.

## Lease rules

A claimed task records `leased_to`, `lease_until` and `heartbeat_at`. A worker renews its lease while active. If the lease expires without a heartbeat, the orchestrator safely requeues the task from its last committed checkpoint.

## Idempotency

Every execution unit receives an idempotency key derived from task ID + checkpoint + attempt. External side effects must be recorded before advancing the checkpoint so retries do not silently duplicate work.

## Review

Review must be independent of the worker when practical. Review evaluates explicit acceptance criteria, tests, artifact existence and deterministic checks. Narrative claims such as 'finished' are not evidence of completion.

## Safety gates

Destructive operations, publication, account changes, payments, security-sensitive changes and other high-impact side effects require an explicit approval node unless a project policy specifically authorizes them.

## Rollout

### Phase 1
- task schema
- PostgreSQL schema
- lease/heartbeat implementation
- queue selection
- event log
- checkpoint/recovery
- CLI worker adapter

### Phase 2
- GitHub adapter
- Marla/Ussylia worker identities
- reviewer adapter
- dependency graph
- retries/backoff
- project manifest discovery

### Phase 3
- dashboard
- scheduled execution
- notifications
- metrics/token accounting
- multi-agent routing
- human approval gates

## Definition of success

The system is successful when a worker can be terminated mid-task, a different worker can resume from the committed checkpoint, duplicate execution is prevented, and the task reaches DONE only after its acceptance criteria independently pass.
