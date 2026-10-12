-- ============================================================
-- Migration 004: Analytics Events + ai_generation_jobs enhancements
-- ============================================================

-- 1. Add analytics-relevant columns to ai_generation_jobs
ALTER TABLE public.ai_generation_jobs
  ADD COLUMN IF NOT EXISTS input_length integer,
  ADD COLUMN IF NOT EXISTS input_tokens integer,
  ADD COLUMN IF NOT EXISTS output_tokens integer,
  ADD COLUMN IF NOT EXISTS retry_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS schema_repair_count integer DEFAULT 0,
  ADD COLUMN IF NOT EXISTS latency_ms integer,
  ADD COLUMN IF NOT EXISTS node_count integer,
  ADD COLUMN IF NOT EXISTS tree_depth integer;

-- 2. Create analytics_events table
CREATE TABLE IF NOT EXISTS public.analytics_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES public.profiles(id) ON DELETE CASCADE,
  session_id uuid NOT NULL,
  knowledge_base_id uuid REFERENCES public.knowledge_bases(id) ON DELETE SET NULL,
  generation_id uuid REFERENCES public.ai_generation_jobs(id) ON DELETE SET NULL,
  mind_map_id uuid REFERENCES public.mind_maps(id) ON DELETE SET NULL,
  event_name text NOT NULL,
  event_time timestamptz NOT NULL DEFAULT now(),
  client_event_id uuid NOT NULL,
  properties jsonb DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Unique constraint for idempotency on client_event_id per user
CREATE UNIQUE INDEX IF NOT EXISTS analytics_events_client_dedup
  ON public.analytics_events (user_id, client_event_id);

-- Query indexes
CREATE INDEX IF NOT EXISTS analytics_events_event_name ON public.analytics_events (event_name);
CREATE INDEX IF NOT EXISTS analytics_events_event_time ON public.analytics_events (event_time);
CREATE INDEX IF NOT EXISTS analytics_events_user_id ON public.analytics_events (user_id);
CREATE INDEX IF NOT EXISTS analytics_events_generation_id ON public.analytics_events (generation_id);
CREATE INDEX IF NOT EXISTS analytics_events_kb_id ON public.analytics_events (knowledge_base_id);

-- 3. RLS
ALTER TABLE public.analytics_events ENABLE ROW LEVEL SECURITY;

-- Users can read only their own analytics events
CREATE POLICY analytics_events_select ON public.analytics_events
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

-- Only backend service_role can insert analytics events
-- (frontend sends events via the backend API which uses the service_role key)

-- 4. Grants
GRANT SELECT ON public.analytics_events TO authenticated;
GRANT ALL ON public.analytics_events TO service_role;
