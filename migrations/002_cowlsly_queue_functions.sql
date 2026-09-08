-- Atomic queue primitives for the Cowlsly durable workflow layer.

CREATE OR REPLACE FUNCTION cowlsly_claim_task(p_worker_id text, p_lease_seconds integer DEFAULT 300)
RETURNS SETOF cowlsly_tasks
LANGUAGE plpgsql
AS $$
DECLARE
  v_task_id text;
BEGIN
  SELECT t.id
  INTO v_task_id
  FROM cowlsly_tasks t
  WHERE t.status = 'READY'
    AND t.attempts < t.max_attempts
    AND NOT EXISTS (
      SELECT 1
      FROM cowlsly_task_dependencies d
      JOIN cowlsly_tasks dep ON dep.id = d.depends_on_task_id
      WHERE d.task_id = t.id AND dep.status <> 'DONE'
    )
  ORDER BY t.priority DESC, t.created_at ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_task_id IS NULL THEN
    RETURN;
  END IF;

  UPDATE cowlsly_tasks
  SET status = 'RUNNING',
      leased_to = p_worker_id,
      heartbeat_at = now(),
      lease_until = now() + make_interval(secs => p_lease_seconds),
      attempts = attempts + 1,
      updated_at = now()
  WHERE id = v_task_id;

  INSERT INTO cowlsly_events(task_id, event_type, payload)
  VALUES (v_task_id, 'task.claimed', jsonb_build_object('worker_id', p_worker_id));

  RETURN QUERY SELECT * FROM cowlsly_tasks WHERE id = v_task_id;
END;
$$;

CREATE OR REPLACE FUNCTION cowlsly_heartbeat(p_task_id text, p_worker_id text, p_lease_seconds integer DEFAULT 300)
RETURNS boolean
LANGUAGE plpgsql
AS $$
DECLARE
  v_count integer;
BEGIN
  UPDATE cowlsly_tasks
  SET heartbeat_at = now(),
      lease_until = now() + make_interval(secs => p_lease_seconds),
      updated_at = now()
  WHERE id = p_task_id
    AND status = 'RUNNING'
    AND leased_to = p_worker_id
    AND lease_until > now();

  GET DIAGNOSTICS v_count = ROW_COUNT;
  IF v_count = 1 THEN
    INSERT INTO cowlsly_events(task_id, event_type, payload)
    VALUES (p_task_id, 'task.heartbeat', jsonb_build_object('worker_id', p_worker_id));
    RETURN true;
  END IF;
  RETURN false;
END;
$$;

CREATE OR REPLACE FUNCTION cowlsly_commit_checkpoint(
  p_task_id text,
  p_worker_id text,
  p_expected_sequence integer,
  p_checkpoint jsonb
)
RETURNS integer
LANGUAGE plpgsql
AS $$
DECLARE
  v_next integer;
BEGIN
  UPDATE cowlsly_tasks
  SET checkpoint = jsonb_set(COALESCE(p_checkpoint, '{}'::jsonb), '{sequence}', to_jsonb(p_expected_sequence + 1), true),
      updated_at = now()
  WHERE id = p_task_id
    AND status = 'RUNNING'
    AND leased_to = p_worker_id
    AND lease_until > now()
    AND COALESCE((checkpoint->>'sequence')::integer, 0) = p_expected_sequence
  RETURNING (checkpoint->>'sequence')::integer INTO v_next;

  IF v_next IS NULL THEN
    RAISE EXCEPTION 'checkpoint conflict or lease lost for task %', p_task_id;
  END IF;

  INSERT INTO cowlsly_events(task_id, event_type, payload)
  VALUES (p_task_id, 'task.checkpoint', jsonb_build_object('worker_id', p_worker_id, 'sequence', v_next));

  RETURN v_next;
END;
$$;

CREATE OR REPLACE FUNCTION cowlsly_recover_expired_leases()
RETURNS TABLE(task_id text, new_status text)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH expired AS (
    UPDATE cowlsly_tasks
    SET status = CASE WHEN attempts < max_attempts THEN 'READY' ELSE 'FAILED' END,
        leased_to = NULL,
        lease_until = NULL,
        updated_at = now()
    WHERE status = 'RUNNING' AND lease_until <= now()
    RETURNING id, status
  ), logged AS (
    INSERT INTO cowlsly_events(task_id, event_type, payload)
    SELECT id, 'task.lease_expired', jsonb_build_object('new_status', status)
    FROM expired
    RETURNING task_id
  )
  SELECT expired.id, expired.status FROM expired;
END;
$$;
