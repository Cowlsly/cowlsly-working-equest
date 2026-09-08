CREATE TABLE IF NOT EXISTS cowlsly_projects (
  id text PRIMARY KEY,
  repository text,
  enabled boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cowlsly_tasks (
  id text PRIMARY KEY,
  project_id text NOT NULL REFERENCES cowlsly_projects(id),
  objective text NOT NULL,
  status text NOT NULL CHECK (status IN ('BLOCKED','READY','LEASED','RUNNING','REVIEW','DONE','FAILED')),
  priority integer NOT NULL DEFAULT 50 CHECK (priority BETWEEN 0 AND 100),
  acceptance_criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
  checkpoint jsonb NOT NULL DEFAULT '{"sequence":0}'::jsonb,
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  leased_to text,
  lease_until timestamptz,
  heartbeat_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cowlsly_task_dependencies (
  task_id text NOT NULL REFERENCES cowlsly_tasks(id) ON DELETE CASCADE,
  depends_on_task_id text NOT NULL REFERENCES cowlsly_tasks(id) ON DELETE CASCADE,
  PRIMARY KEY (task_id, depends_on_task_id),
  CHECK (task_id <> depends_on_task_id)
);

CREATE TABLE IF NOT EXISTS cowlsly_task_runs (
  id bigserial PRIMARY KEY,
  task_id text NOT NULL REFERENCES cowlsly_tasks(id),
  worker_id text NOT NULL,
  checkpoint_sequence integer NOT NULL,
  attempt integer NOT NULL,
  idempotency_key text NOT NULL UNIQUE,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  outcome text,
  error jsonb
);

CREATE TABLE IF NOT EXISTS cowlsly_events (
  id bigserial PRIMARY KEY,
  task_id text REFERENCES cowlsly_tasks(id),
  run_id bigint REFERENCES cowlsly_task_runs(id),
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cowlsly_artifacts (
  id bigserial PRIMARY KEY,
  task_id text NOT NULL REFERENCES cowlsly_tasks(id),
  run_id bigint REFERENCES cowlsly_task_runs(id),
  uri text NOT NULL,
  sha256 text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS cowlsly_agents (
  id text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT true,
  capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
  last_seen_at timestamptz
);

CREATE INDEX IF NOT EXISTS cowlsly_tasks_ready_idx ON cowlsly_tasks(priority DESC, created_at ASC) WHERE status = 'READY';
CREATE INDEX IF NOT EXISTS cowlsly_tasks_lease_idx ON cowlsly_tasks(lease_until) WHERE status IN ('LEASED','RUNNING');
CREATE INDEX IF NOT EXISTS cowlsly_events_task_idx ON cowlsly_events(task_id, created_at);

-- Workers should claim work inside a transaction using SELECT ... FOR UPDATE SKIP LOCKED.
-- A runnable task is READY and has no dependency whose status is not DONE.
