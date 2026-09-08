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
- [x] Run the new tests in focused CI and fix runner/dependency failures.
- [ ] Exercise PostgreSQL functions against a real Neon branch.

## P1: worker/reviewer
- [x] Worker adapter interface.
- [x] Reviewer adapter interface.
- [x] Acceptance-criteria result format.
- [x] Retry/backoff policy.
- [x] Dependency resolver cycle detection.
- [x] SHA-256 artifact hashing helper.
- [x] Persist artifact registration records in the PostgreSQL queue backend.
- [x] Marla worker profile.
- [x] Ussylia worker profile.
- [x] Meta provider profile (disabled until API access is configured).
- [x] Initial capability-based worker selector.
- [x] Initial durable dispatcher.
- [x] Dispatcher review-path tests.

## P2: GitHub integration
- [x] Define `.cowlsly/workflow.json` opt-in manifest and schema.
- [x] Add fail-closed manifest parsing, archived-repo rejection and safe relative-path checks.
- [x] Support repositories whose default branch is not `main`.
- [x] Add task-contract ingestion with duplicate-ID, dependency and cycle validation.
- [x] Add GitHub REST source for owned public/private repository enumeration.
- [x] Fetch manifests and task JSON from each repository's actual default branch.
- [x] Add bootstrap pipeline that combines multiple task files before dependency validation.
- [x] Persist imported projects/tasks into the PostgreSQL queue backend without resetting live execution state.
- [ ] Write human-readable task status back to GitHub.
- [ ] Link commits/PRs/issues to task runs.
- [ ] Never overwrite project TODO files without preserving human edits.

## P3: operation
- [x] Bounded scheduler around the durable dispatcher.
- [x] Scheduler tests for empty queue, dispatch limits and stop requests.
- [ ] Attach scheduler tick to DeterminFlow automation/cron.
- [ ] Dashboard for READY/RUNNING/BLOCKED/REVIEW/FAILED/DONE.
- [ ] Metrics and token/cost ledger.
- [ ] Human approval queue.
- [ ] Notifications for failed/stalled/approval-required work.

## Current external blockers
- Focused GitHub Actions durable-core run is now passing. Keep the PR open until the broader repository CI is also green and the remaining live integration work is exercised.
- Neon is connected, but the account requires an organization ID before projects can be enumerated. Do not guess a production target.

## Exit tests
1. Kill worker A midway through a task.
2. Wait for lease expiry.
3. Worker B claims the same task.
4. Worker B resumes from the committed checkpoint rather than restarting.
5. No external side effect is duplicated.
6. Reviewer rejects an intentionally incomplete artifact.
7. Task reaches DONE only after all acceptance criteria pass.
