# Cowlsly Durable Workflow — Implementation TODO

## P0: foundation
- [x] Define state machine and worker protocol.
- [x] Define JSON task contract.
- [x] Define PostgreSQL persistence schema.
- [x] Implement atomic `claim_task(worker_id, lease_seconds)` using `FOR UPDATE SKIP LOCKED`.
- [x] Implement heartbeat/lease renewal.
- [x] Implement expired-lease recovery.
- [x] Implement checkpoint commit with optimistic sequence check.
- [x] Implement append-only event writer.
- [x] Add idempotency protection for retries.
- [x] Add unit tests for two workers racing for one task.
- [x] Add crash/restart recovery test semantics.
- [ ] Run the new tests in CI and fix any integration failures.
- [ ] Exercise PostgreSQL functions against a real Neon branch.

## P1: worker/reviewer
- [x] Worker adapter interface.
- [x] Reviewer adapter interface.
- [x] Acceptance-criteria result format.
- [ ] Retry/backoff policy.
- [ ] Dependency resolver and cycle detection.
- [ ] Artifact registration with SHA-256.
- [x] Marla worker profile.
- [x] Ussylia worker profile.
- [x] Meta provider profile (disabled until API access is configured).
- [x] Initial capability-based worker selector.

## P2: GitHub integration
- [ ] Discover project manifests.
- [ ] Import task contracts from opted-in repositories.
- [ ] Write human-readable task status back to GitHub.
- [ ] Link commits/PRs/issues to task runs.
- [ ] Never overwrite project TODO files without preserving human edits.

## P3: operation
- [ ] Scheduler/dispatcher.
- [ ] Dashboard for READY/RUNNING/BLOCKED/REVIEW/FAILED/DONE.
- [ ] Metrics and token/cost ledger.
- [ ] Human approval queue.
- [ ] Notifications for failed/stalled/approval-required work.

## Exit tests
1. Kill worker A midway through a task.
2. Wait for lease expiry.
3. Worker B claims the same task.
4. Worker B resumes from the committed checkpoint rather than restarting.
5. No external side effect is duplicated.
6. Reviewer rejects an intentionally incomplete artifact.
7. Task reaches DONE only after all acceptance criteria pass.
