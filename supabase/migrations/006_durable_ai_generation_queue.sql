-- Migration 006: durable AI generation queue and atomic worker coordination.
--
-- This migration deliberately reuses ai_generation_jobs. It does not create a
-- second queue. Existing pending/running rows are preserved as failed audit
-- history; new work uses the closed queued/running/succeeded/failed lifecycle.

ALTER TABLE public.ai_generation_jobs
  ADD COLUMN IF NOT EXISTS operation text,
  ADD COLUMN IF NOT EXISTS client_request_id uuid,
  ADD COLUMN IF NOT EXISTS request_payload jsonb,
  ADD COLUMN IF NOT EXISTS queued_at timestamptz,
  ADD COLUMN IF NOT EXISTS locked_at timestamptz,
  ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz,
  ADD COLUMN IF NOT EXISTS worker_id text,
  ADD COLUMN IF NOT EXISTS claim_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS queue_wait_ms integer,
  ADD COLUMN IF NOT EXISTS generation_latency_ms integer,
  ADD COLUMN IF NOT EXISTS total_latency_ms integer,
  ADD COLUMN IF NOT EXISTS provider_status integer,
  ADD COLUMN IF NOT EXISTS first_attempt_success boolean,
  ADD COLUMN IF NOT EXISTS retry_recovered boolean,
  ADD COLUMN IF NOT EXISTS llm_call_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS actual_depth integer,
  ADD COLUMN IF NOT EXISTS result_mind_map_id uuid;

UPDATE public.ai_generation_jobs
SET queued_at = COALESCE(queued_at, created_at)
WHERE queued_at IS NULL;

-- Never execute legacy HTTP-request jobs after the queue is enabled. Preserve
-- every historical row, but close legacy pending/running state deterministically
-- so it cannot block capacity or be claimed by the new Worker.
UPDATE public.ai_generation_jobs
SET status = 'failed',
    error_code = COALESCE(error_code, 'LEGACY_JOB_NOT_EXECUTED'),
    error_message = COALESCE(error_message, 'Legacy synchronous generation was not resumed during queue migration.'),
    error_stage = COALESCE(error_stage, 'migration_legacy_active'),
    finished_at = COALESCE(finished_at, now()),
    updated_at = now()
WHERE status IN ('pending', 'running');

ALTER TABLE public.ai_generation_jobs
  DROP CONSTRAINT IF EXISTS ai_generation_jobs_status_check;

ALTER TABLE public.ai_generation_jobs
  ADD CONSTRAINT ai_generation_jobs_status_check
  CHECK (status IN ('queued', 'running', 'succeeded', 'failed'));

ALTER TABLE public.ai_generation_jobs
  DROP CONSTRAINT IF EXISTS ai_generation_jobs_operation_check;

ALTER TABLE public.ai_generation_jobs
  ADD CONSTRAINT ai_generation_jobs_operation_check
  CHECK (operation IS NULL OR operation IN ('generate', 'regenerate'));

ALTER TABLE public.ai_generation_jobs
  DROP CONSTRAINT IF EXISTS ai_generation_jobs_requested_depth_range;

ALTER TABLE public.ai_generation_jobs
  ADD CONSTRAINT ai_generation_jobs_requested_depth_range
  CHECK (requested_depth IS NULL OR requested_depth BETWEEN 3 AND 6);

ALTER TABLE public.ai_generation_jobs
  DROP CONSTRAINT IF EXISTS ai_generation_jobs_result_mind_map_fk;

ALTER TABLE public.ai_generation_jobs
  ADD CONSTRAINT ai_generation_jobs_result_mind_map_fk
  FOREIGN KEY (result_mind_map_id) REFERENCES public.mind_maps(id) ON DELETE SET NULL;

ALTER TABLE public.mind_maps
  ADD COLUMN IF NOT EXISTS generation_job_id uuid;

ALTER TABLE public.mind_maps
  DROP CONSTRAINT IF EXISTS mind_maps_generation_job_fk;

ALTER TABLE public.mind_maps
  ADD CONSTRAINT mind_maps_generation_job_fk
  FOREIGN KEY (generation_job_id) REFERENCES public.ai_generation_jobs(id) ON DELETE SET NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ai_generation_jobs_request_id_unique
  ON public.ai_generation_jobs (user_id, operation, client_request_id)
  WHERE client_request_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS mind_maps_generation_job_unique
  ON public.mind_maps (generation_job_id)
  WHERE generation_job_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ai_generation_jobs_queue_fifo
  ON public.ai_generation_jobs (status, created_at, id)
  WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS ai_generation_jobs_stale_lease
  ON public.ai_generation_jobs (status, lease_expires_at, id)
  WHERE status = 'running';

CREATE INDEX IF NOT EXISTS ai_generation_jobs_user_active
  ON public.ai_generation_jobs (user_id, status, created_at, id)
  WHERE status IN ('queued', 'running');

CREATE INDEX IF NOT EXISTS ai_generation_jobs_result_lookup
  ON public.ai_generation_jobs (result_mind_map_id)
  WHERE result_mind_map_id IS NOT NULL;

-- One transaction-scoped lock serializes capacity decisions across all Web
-- processes/replicas. The Provider cap is therefore not process-local.
DROP FUNCTION IF EXISTS public.enqueue_ai_generation_job(uuid, uuid, text, uuid, jsonb, integer, integer);

CREATE OR REPLACE FUNCTION public.enqueue_ai_generation_job(
  p_user_id uuid,
  p_knowledge_base_id uuid,
  p_operation text,
  p_client_request_id uuid,
  p_request_payload jsonb,
  p_model_name text,
  p_prompt_version text,
  p_max_active_jobs integer,
  p_max_queue_size integer
)
RETURNS TABLE(job_id uuid, status text, created boolean, reason text)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  existing_job public.ai_generation_jobs%ROWTYPE;
  active_count integer;
  queue_count integer;
BEGIN
  IF p_operation NOT IN ('generate', 'regenerate') THEN
    RETURN QUERY SELECT NULL::uuid, 'rejected'::text, false, 'invalid_operation'::text;
    RETURN;
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('knowledge-bar-ai-generation-queue', 0)
  );

  SELECT * INTO existing_job
  FROM public.ai_generation_jobs
  WHERE user_id = p_user_id
    AND operation = p_operation
    AND client_request_id = p_client_request_id
  LIMIT 1;

  IF existing_job.id IS NOT NULL THEN
    RETURN QUERY SELECT existing_job.id, existing_job.status, false, 'existing'::text;
    RETURN;
  END IF;

  SELECT count(*)::integer INTO active_count
  FROM public.ai_generation_jobs
  WHERE user_id = p_user_id
    AND status IN ('queued', 'running');

  IF active_count >= greatest(coalesce(p_max_active_jobs, 1), 1) THEN
    RETURN QUERY SELECT NULL::uuid, 'rejected'::text, false, 'user_capacity'::text;
    RETURN;
  END IF;

  SELECT count(*)::integer INTO queue_count
  FROM public.ai_generation_jobs
  WHERE status IN ('queued', 'running');

  IF queue_count >= greatest(coalesce(p_max_queue_size, 1), 1) THEN
    RETURN QUERY SELECT NULL::uuid, 'rejected'::text, false, 'queue_capacity'::text;
    RETURN;
  END IF;

  RETURN QUERY
  INSERT INTO public.ai_generation_jobs AS j (
    user_id,
    knowledge_base_id,
    operation,
    client_request_id,
    request_payload,
    requested_depth,
    status,
    model_name,
    prompt_version,
    queued_at,
    created_at,
    updated_at
  )
  VALUES (
    p_user_id,
    p_knowledge_base_id,
    p_operation,
    p_client_request_id,
    p_request_payload,
    (p_request_payload->>'requested_max_depth')::integer,
    'queued',
    p_model_name,
    p_prompt_version,
    now(),
    now(),
    now()
  )
  RETURNING j.id, j.status, true, 'created'::text;
END;
$$;

-- Recover expired leases without deleting history. A crashed worker is
-- requeued a bounded number of times; after the bound the poison Job is
-- terminally failed and cannot generate indefinitely.
CREATE OR REPLACE FUNCTION public.recover_stale_ai_jobs(
  p_max_claims integer DEFAULT 3
)
RETURNS SETOF public.ai_generation_jobs
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('knowledge-bar-ai-generation-queue', 0)
  );

  RETURN QUERY
  UPDATE public.ai_generation_jobs
  SET status = CASE
        WHEN coalesce(claim_count, 0) >= greatest(coalesce(p_max_claims, 3), 1)
          THEN 'failed'
        ELSE 'queued'
      END,
      error_code = CASE
        WHEN coalesce(claim_count, 0) >= greatest(coalesce(p_max_claims, 3), 1)
          THEN 'AI_JOB_LEASE_EXPIRED'
        ELSE error_code
      END,
      error_message = CASE
        WHEN coalesce(claim_count, 0) >= greatest(coalesce(p_max_claims, 3), 1)
          THEN 'AI generation worker lease expired too many times.'
        ELSE error_message
      END,
      error_stage = CASE
        WHEN coalesce(claim_count, 0) >= greatest(coalesce(p_max_claims, 3), 1)
          THEN 'worker_recovery'
        ELSE error_stage
      END,
      finished_at = CASE
        WHEN coalesce(claim_count, 0) >= greatest(coalesce(p_max_claims, 3), 1)
          THEN now()
        ELSE finished_at
      END,
      worker_id = NULL,
      locked_at = NULL,
      lease_expires_at = NULL,
      heartbeat_at = now(),
      updated_at = now()
  WHERE status = 'running'
    AND lease_expires_at IS NOT NULL
    AND lease_expires_at < now()
  RETURNING *;
END;
$$;

-- Claim FIFO work and enforce the measured global Provider cap. A stale lease
-- is requeued before new work is claimed; result persistence is idempotent.
DROP FUNCTION IF EXISTS public.claim_ai_generation_jobs(text, integer, integer);

CREATE OR REPLACE FUNCTION public.claim_ai_generation_jobs(
  p_worker_id text,
  p_global_limit integer,
  p_claim_limit integer,
  p_lease_seconds integer
)
RETURNS SETOF public.ai_generation_jobs
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  running_count integer;
  available_count integer;
BEGIN
  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('knowledge-bar-ai-generation-queue', 0)
  );

  PERFORM public.recover_stale_ai_jobs(3);

  SELECT count(*)::integer INTO running_count
  FROM public.ai_generation_jobs
  WHERE status = 'running'
    AND (lease_expires_at IS NULL OR lease_expires_at >= now());

  available_count := greatest(
    least(
      least(greatest(coalesce(p_global_limit, 1), 1), 100) - running_count,
      least(greatest(coalesce(p_claim_limit, 1), 1), 100)
    ),
    0
  );
  IF available_count = 0 THEN
    RETURN;
  END IF;

  RETURN QUERY
  WITH candidates AS (
    SELECT id
    FROM public.ai_generation_jobs
    WHERE status = 'queued'
    ORDER BY created_at, id
    FOR UPDATE SKIP LOCKED
    LIMIT available_count
  )
  UPDATE public.ai_generation_jobs j
  SET status = 'running',
      started_at = COALESCE(j.started_at, now()),
      locked_at = now(),
      lease_expires_at = now() + make_interval(secs => greatest(coalesce(p_lease_seconds, 120), 30)),
      heartbeat_at = now(),
      worker_id = p_worker_id,
      claim_count = coalesce(j.claim_count, 0) + 1,
      updated_at = now()
  FROM candidates c
  WHERE j.id = c.id
  RETURNING j.*;
END;
$$;

CREATE OR REPLACE FUNCTION public.heartbeat_ai_generation_job(
  p_job_id uuid,
  p_worker_id text,
  p_lease_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
BEGIN
  UPDATE public.ai_generation_jobs
  SET heartbeat_at = now(),
      lease_expires_at = now() + make_interval(secs => greatest(coalesce(p_lease_seconds, 120), 30)),
      updated_at = now()
  WHERE id = p_job_id
    AND status = 'running'
    AND worker_id = p_worker_id;
  RETURN FOUND;
END;
$$;

CREATE OR REPLACE FUNCTION public.fail_ai_generation_job(
  p_job_id uuid,
  p_worker_id text,
  p_error_code text,
  p_error_message text,
  p_error_stage text,
  p_retry_count integer,
  p_total_latency_ms integer,
  p_metrics jsonb
)
RETURNS public.ai_generation_jobs
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  result_row public.ai_generation_jobs;
BEGIN
  UPDATE public.ai_generation_jobs
  SET status = 'failed',
      error_code = p_error_code,
      error_message = left(p_error_message, 1000),
      error_stage = p_error_stage,
      retry_count = coalesce(p_retry_count, retry_count, 0),
      total_latency_ms = p_total_latency_ms,
      queue_wait_ms = coalesce((extract(epoch FROM (coalesce(started_at, now()) - queued_at)) * 1000)::integer, queue_wait_ms),
      generation_latency_ms = coalesce((p_metrics->>'generation_latency_ms')::integer, generation_latency_ms),
      provider_status = coalesce((p_metrics->>'provider_status')::integer, provider_status),
      first_attempt_success = coalesce((p_metrics->>'first_attempt_success')::boolean, first_attempt_success),
      retry_recovered = coalesce((p_metrics->>'retry_recovered')::boolean, retry_recovered),
      llm_call_count = coalesce((p_metrics->>'llm_call_count')::integer, llm_call_count, 0),
      input_length = coalesce((p_metrics->>'input_length')::integer, input_length),
      schema_repair_count = coalesce((p_metrics->>'schema_repair_count')::integer, schema_repair_count, 0),
      repair_attempted = coalesce((p_metrics->>'repair_attempted')::boolean, repair_attempted, false),
      repair_success = coalesce((p_metrics->>'repair_success')::boolean, repair_success, false),
      finished_at = now(),
      locked_at = NULL,
      lease_expires_at = NULL,
      heartbeat_at = now(),
      updated_at = now()
  WHERE id = p_job_id
    AND status = 'running'
    AND worker_id = p_worker_id
  RETURNING * INTO result_row;

  IF result_row.id IS NULL THEN
    RAISE EXCEPTION 'job_not_owned_or_not_running';
  END IF;
  RETURN result_row;
END;
$$;

-- Persist one MindMap version and mark the Job succeeded in one transaction.
-- A per-KB advisory lock serializes version allocation without a second queue.
CREATE OR REPLACE FUNCTION public.complete_ai_generation_job(
  p_job_id uuid,
  p_worker_id text,
  p_data_jsonb jsonb,
  p_markdown text,
  p_metrics jsonb
)
RETURNS TABLE(job_id uuid, status text, mind_map_id uuid, version_no integer)
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public
AS $$
DECLARE
  job_row public.ai_generation_jobs%ROWTYPE;
  existing_map public.mind_maps%ROWTYPE;
  new_map_id uuid;
  new_version integer;
BEGIN
  SELECT * INTO job_row
  FROM public.ai_generation_jobs
  WHERE id = p_job_id
  FOR UPDATE;

  IF job_row.id IS NULL THEN
    RAISE EXCEPTION 'job_not_found';
  END IF;

  IF job_row.result_mind_map_id IS NOT NULL THEN
    SELECT * INTO existing_map FROM public.mind_maps WHERE id = job_row.result_mind_map_id;
    RETURN QUERY SELECT job_row.id, 'succeeded'::text, existing_map.id, existing_map.version_no;
    RETURN;
  END IF;

  IF job_row.status <> 'running' OR job_row.worker_id <> p_worker_id THEN
    RAISE EXCEPTION 'job_not_owned_or_not_running';
  END IF;

  PERFORM pg_catalog.pg_advisory_xact_lock(
    pg_catalog.hashtextextended('knowledge-bar-kb-' || job_row.knowledge_base_id::text, 0)
  );

  SELECT coalesce(max(version_no), 0) + 1 INTO new_version
  FROM public.mind_maps
  WHERE user_id = job_row.user_id
    AND knowledge_base_id = job_row.knowledge_base_id;

  INSERT INTO public.mind_maps (
    user_id,
    knowledge_base_id,
    generation_job_id,
    data_jsonb,
    markdown,
    version_no,
    created_at,
    updated_at
  )
  VALUES (
    job_row.user_id,
    job_row.knowledge_base_id,
    job_row.id,
    p_data_jsonb,
    coalesce(p_markdown, ''),
    new_version,
    now(),
    now()
  )
  RETURNING id INTO new_map_id;

  UPDATE public.ai_generation_jobs
  SET status = 'succeeded',
      result_mind_map_id = new_map_id,
      error_code = NULL,
      error_message = NULL,
      error_stage = NULL,
      input_length = coalesce((p_metrics->>'input_length')::integer, input_length),
      input_tokens = coalesce((p_metrics->>'input_tokens')::integer, input_tokens),
      output_tokens = coalesce((p_metrics->>'output_tokens')::integer, output_tokens),
      retry_count = coalesce((p_metrics->>'retry_count')::integer, retry_count, 0),
      schema_repair_count = coalesce((p_metrics->>'schema_repair_count')::integer, schema_repair_count, 0),
      repair_attempted = coalesce((p_metrics->>'repair_attempted')::boolean, repair_attempted, false),
      repair_success = coalesce((p_metrics->>'repair_success')::boolean, repair_success, false),
      latency_ms = coalesce((p_metrics->>'latency_ms')::integer, latency_ms),
      generation_latency_ms = coalesce((p_metrics->>'generation_latency_ms')::integer, generation_latency_ms),
      total_latency_ms = coalesce((p_metrics->>'total_latency_ms')::integer, total_latency_ms),
      node_count = coalesce((p_metrics->>'node_count')::integer, node_count),
      tree_depth = coalesce((p_metrics->>'tree_depth')::integer, tree_depth),
      actual_depth = coalesce((p_metrics->>'actual_depth')::integer, actual_depth),
      provider_status = coalesce((p_metrics->>'provider_status')::integer, provider_status),
      first_attempt_success = coalesce((p_metrics->>'first_attempt_success')::boolean, first_attempt_success),
      retry_recovered = coalesce((p_metrics->>'retry_recovered')::boolean, retry_recovered),
      llm_call_count = coalesce((p_metrics->>'llm_call_count')::integer, llm_call_count, 0),
      finished_at = now(),
      locked_at = NULL,
      lease_expires_at = NULL,
      heartbeat_at = now(),
      updated_at = now()
  WHERE id = p_job_id
    AND status = 'running'
    AND worker_id = p_worker_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'job_not_owned_or_not_running';
  END IF;

  RETURN QUERY SELECT p_job_id, 'succeeded'::text, new_map_id, new_version;
END;
$$;

REVOKE ALL ON FUNCTION public.enqueue_ai_generation_job(uuid, uuid, text, uuid, jsonb, text, text, integer, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.recover_stale_ai_jobs(integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.claim_ai_generation_jobs(text, integer, integer, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.heartbeat_ai_generation_job(uuid, text, integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.fail_ai_generation_job(uuid, text, text, text, text, integer, integer, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.complete_ai_generation_job(uuid, text, jsonb, text, jsonb) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.enqueue_ai_generation_job(uuid, uuid, text, uuid, jsonb, text, text, integer, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.recover_stale_ai_jobs(integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.claim_ai_generation_jobs(text, integer, integer, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.heartbeat_ai_generation_job(uuid, text, integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.fail_ai_generation_job(uuid, text, text, text, text, integer, integer, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.complete_ai_generation_job(uuid, text, jsonb, text, jsonb) TO service_role;
