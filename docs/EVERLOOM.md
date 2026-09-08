# Everloom

Everloom (`cowlsly-everloom`) is Cowlsly's durable AI workflow skill for work that must survive interrupted sessions, worker changes and retries.

## What it guarantees

Everloom stores task state outside an individual model conversation. Work is leased to a worker for a bounded period, checkpointed, audited through events, and resumed by another capable worker when necessary. Completion is controlled by explicit acceptance criteria and review.

The authoritative AI-facing operating contract is `skills/everloom/SKILL.md`.

## Opt a repository in

Add `.cowlsly/workflow.json` to the repository and point it at one or more task JSON files. Repositories without a valid enabled manifest are ignored. Task IDs, dependency graphs, paths and acceptance criteria are validated before import.

This repository opts Everloom into itself. Its release task graph is `.cowlsly/tasks/everloom-release.json`, allowing Everloom's own remaining work to be represented using the same durable contract.

## Runtime pieces

- `durable_discovery.py`: fail-closed project discovery and manifest validation.
- `durable_ingestion.py`: task parsing and dependency validation.
- `durable_store.py`: PostgreSQL persistence for imported definitions and artifact records.
- `durable_queue.py` plus SQL migrations: lease, heartbeat, checkpoint and recovery semantics.
- `durable_workers.py`: worker/reviewer contracts and capability profiles.
- `durable_dispatcher.py`: bounded task execution and review routing.
- `durable_scheduler.py`: repeated bounded dispatch ticks.
- `durable_github.py`: GitHub repository and task-source adapter.
- `durable_bootstrap.py`: discovery-to-persistence bootstrap handoff.

## Recovery

A worker owns a RUNNING task only while its lease is valid. It heartbeats during active work and commits monotonic checkpoints. If it disappears, lease recovery returns the task to READY when attempts remain. A replacement worker loads the persisted checkpoint instead of depending on the previous model's private conversation history.

External side effects must use idempotency protection so a resumed task does not duplicate an operation already completed before an interruption.

## Review

Reviewers evaluate declared acceptance criteria. A rejection returns actionable feedback and makes the task eligible for another bounded attempt. DONE means criteria passed, not merely that a worker stopped producing output.

## Build the storage package

Run:

```bash
python scripts/package_everloom.py --output dist/everloom-1.0.0.zip
python scripts/package_everloom.py --validate-only dist/everloom-1.0.0.zip
```

The packager uses an explicit allow-list, writes `EVERLOOM-MANIFEST.json`, hashes included files with SHA-256, and rejects unsafe/private paths. ZIP timestamps are normalized so the same revision and environment produce stable archive content.

GitHub Actions runs the focused tests, builds and validates the archive, then uploads `everloom-1.0.0` as a downloadable workflow artifact retained for 90 days.

## Install or teach an AI

Give the AI access to the extracted package and instruct it to load `skills/everloom/SKILL.md` as the Everloom operating skill. The skill is deliberately host-neutral: it defines durable behavior but does not grant permissions. The host still controls available tools, credentials, databases and approval boundaries.

## External deployment

The core package can be built and tested without production credentials. A live deployment additionally needs a PostgreSQL target (Neon is suitable), database migrations applied to that target, and whatever GitHub/API credentials the chosen host authorizes. Those are deployment choices and secrets, not embedded in the package.

Never put `.env` files, API tokens, database credentials or private runtime data into an Everloom archive.
