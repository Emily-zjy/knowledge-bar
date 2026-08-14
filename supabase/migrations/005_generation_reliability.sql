-- Persist generation reliability stages and depth evidence.
-- Safe to apply after 004_analytics_events.sql.

ALTER TABLE public.ai_generation_jobs
  ADD COLUMN IF NOT EXISTS error_stage text,
  ADD COLUMN IF NOT EXISTS requested_depth integer,
  ADD COLUMN IF NOT EXISTS repair_attempted boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS repair_success boolean NOT NULL DEFAULT false;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'ai_generation_jobs_requested_depth_range'
  ) THEN
    ALTER TABLE public.ai_generation_jobs
      ADD CONSTRAINT ai_generation_jobs_requested_depth_range
      CHECK (requested_depth IS NULL OR requested_depth BETWEEN 3 AND 6);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_generation_jobs_error_stage
  ON public.ai_generation_jobs (error_stage, created_at DESC)
  WHERE status = 'failed';
