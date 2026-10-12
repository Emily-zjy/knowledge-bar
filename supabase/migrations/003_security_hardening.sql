-- 003_security_hardening.sql
-- Depends on: 001_initial_schema.sql, 002_mind_maps_multi_version.sql
-- This migration hardens security: profile auto-creation trigger, refined RLS
-- with explicit TO authenticated, cross-table ownership checks, GRANT/REVOKE,
-- storage policies, and function security.
--
-- DO NOT auto-apply. Review and execute manually in Supabase SQL Editor.

-- ============================================================
-- 1. Profile auto-creation trigger (auth.users AFTER INSERT)
-- ============================================================

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
-- SECURITY DEFINER is required because this trigger fires from auth schema
-- and needs to INSERT into public.profiles which the new user cannot yet access.
SET search_path = ''
AS $$
BEGIN
  INSERT INTO public.profiles (id, nickname, created_at, updated_at)
  VALUES (
    NEW.id,
    COALESCE(SPLIT_PART(NEW.email, '@', 1), 'user'),
    NOW(),
    NOW()
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$;

-- Revoke direct EXECUTE from roles that should not call this function manually
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM authenticated;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- Backfill: create profiles for any auth.users that don't have one yet
INSERT INTO public.profiles (id, nickname, created_at, updated_at)
SELECT
  u.id,
  COALESCE(SPLIT_PART(u.email, '@', 1), 'user'),
  COALESCE(u.created_at, NOW()),
  NOW()
FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id)
ON CONFLICT (id) DO NOTHING;

-- ============================================================
-- 2. Fix set_updated_at() function — secure search_path
-- ============================================================

CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$;

-- This is a utility function; no SECURITY DEFINER needed.
-- Revoke from anon (it only fires via triggers, not direct calls).
REVOKE EXECUTE ON FUNCTION public.set_updated_at() FROM anon;

-- ============================================================
-- 3. Enable RLS on all 7 tables (idempotent)
-- ============================================================

ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_bases ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.knowledge_base_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.attachments ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.mind_maps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_generation_jobs ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- 4. Drop old policies from 001 (they lack TO authenticated)
-- ============================================================

DROP POLICY IF EXISTS "profiles own select" ON public.profiles;
DROP POLICY IF EXISTS "profiles own update" ON public.profiles;
DROP POLICY IF EXISTS "profiles own insert" ON public.profiles;
DROP POLICY IF EXISTS "knowledge_bases own all" ON public.knowledge_bases;
DROP POLICY IF EXISTS "tags own all" ON public.tags;
DROP POLICY IF EXISTS "knowledge_base_tags own all" ON public.knowledge_base_tags;
DROP POLICY IF EXISTS "attachments own all" ON public.attachments;
DROP POLICY IF EXISTS "mind_maps own all" ON public.mind_maps;
DROP POLICY IF EXISTS "ai_generation_jobs own all" ON public.ai_generation_jobs;

-- ============================================================
-- 5. New RLS Policies — explicit TO authenticated, per-operation
-- ============================================================

-- --- profiles ---
CREATE POLICY profiles_select ON public.profiles
  FOR SELECT TO authenticated
  USING (auth.uid() = id);

CREATE POLICY profiles_insert ON public.profiles
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = id);

CREATE POLICY profiles_update ON public.profiles
  FOR UPDATE TO authenticated
  USING (auth.uid() = id)
  WITH CHECK (auth.uid() = id);

-- --- knowledge_bases ---
CREATE POLICY kb_select ON public.knowledge_bases
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY kb_insert ON public.knowledge_bases
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY kb_update ON public.knowledge_bases
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY kb_delete ON public.knowledge_bases
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- --- tags ---
CREATE POLICY tags_select ON public.tags
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY tags_insert ON public.tags
  FOR INSERT TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY tags_update ON public.tags
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY tags_delete ON public.tags
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- --- knowledge_base_tags (cross-table: KB and tag must belong to user) ---
CREATE POLICY kbt_select ON public.knowledge_base_tags
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY kbt_insert ON public.knowledge_base_tags
  FOR INSERT TO authenticated
  WITH CHECK (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
    AND EXISTS (SELECT 1 FROM public.tags t WHERE t.id = tag_id AND t.user_id = auth.uid())
  );

CREATE POLICY kbt_update ON public.knowledge_base_tags
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
    AND EXISTS (SELECT 1 FROM public.tags t WHERE t.id = tag_id AND t.user_id = auth.uid())
  );

CREATE POLICY kbt_delete ON public.knowledge_base_tags
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- --- attachments (cross-table: KB must belong to user) ---
CREATE POLICY att_select ON public.attachments
  FOR SELECT TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY att_insert ON public.attachments
  FOR INSERT TO authenticated
  WITH CHECK (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
  );

CREATE POLICY att_update ON public.attachments
  FOR UPDATE TO authenticated
  USING (auth.uid() = user_id)
  WITH CHECK (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
  );

CREATE POLICY att_delete ON public.attachments
  FOR DELETE TO authenticated
  USING (auth.uid() = user_id);

-- --- mind_maps (cross-table: KB must belong to user) ---
-- Frontend authenticated users only need SELECT (all writes via backend service role).
CREATE POLICY mm_select ON public.mind_maps
  FOR SELECT TO authenticated
  USING (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
  );

-- INSERT/UPDATE/DELETE are performed by the backend using the service_role key,
-- which bypasses RLS. No authenticated policy needed for writes.

-- --- ai_generation_jobs (cross-table: KB must belong to user) ---
-- Frontend authenticated users only need SELECT (all writes via backend service role).
CREATE POLICY gj_select ON public.ai_generation_jobs
  FOR SELECT TO authenticated
  USING (
    auth.uid() = user_id
    AND EXISTS (SELECT 1 FROM public.knowledge_bases kb WHERE kb.id = knowledge_base_id AND kb.user_id = auth.uid())
  );

-- INSERT/UPDATE are performed by the backend using the service_role key.

-- ============================================================
-- 6. GRANT / REVOKE — minimum privilege
-- ============================================================

-- Revoke schema USAGE from PUBLIC and anon so they cannot discover objects.
REVOKE USAGE ON SCHEMA public FROM PUBLIC, anon;

-- Grant schema USAGE only to authenticated and service_role.
GRANT USAGE ON SCHEMA public TO authenticated, service_role;

-- Revoke all default grants from PUBLIC and anon on business tables.
REVOKE ALL ON TABLE
  public.profiles,
  public.knowledge_bases,
  public.tags,
  public.knowledge_base_tags,
  public.attachments,
  public.mind_maps,
  public.ai_generation_jobs
FROM PUBLIC, anon;

-- authenticated: grant only what the frontend Data API actually needs.
-- (RLS further restricts row access within these grants.)
-- profiles: SELECT+UPDATE only; INSERT is handled by auth.users trigger,
-- DELETE is forbidden to prevent cascade-deleting all user data.
GRANT SELECT, UPDATE ON public.profiles TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_bases TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tags TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.knowledge_base_tags TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.attachments TO authenticated;
-- mind_maps: authenticated only reads; backend writes with service_role
GRANT SELECT ON public.mind_maps TO authenticated;
-- ai_generation_jobs: authenticated only reads; backend writes with service_role
GRANT SELECT ON public.ai_generation_jobs TO authenticated;

-- service_role: explicit CRUD on all business tables.
-- BYPASSRLS only bypasses row-level policies; table-level GRANTs are still required.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE
  public.profiles,
  public.knowledge_bases,
  public.tags,
  public.knowledge_base_tags,
  public.attachments,
  public.mind_maps,
  public.ai_generation_jobs
TO service_role;

-- ============================================================
-- 7. Storage — private bucket with per-user path isolation
-- ============================================================

-- Ensure bucket exists and is private (idempotent)
INSERT INTO storage.buckets (id, name, public)
VALUES ('knowledge-bar-assets', 'knowledge-bar-assets', false)
ON CONFLICT (id) DO UPDATE SET public = false;

-- Drop old policies from 001 and recreate with TO authenticated
DROP POLICY IF EXISTS "knowledge bar assets own select" ON storage.objects;
DROP POLICY IF EXISTS "knowledge bar assets own insert" ON storage.objects;
DROP POLICY IF EXISTS "knowledge bar assets own update" ON storage.objects;
DROP POLICY IF EXISTS "knowledge bar assets own delete" ON storage.objects;

CREATE POLICY "kb_assets_select" ON storage.objects
  FOR SELECT TO authenticated
  USING (
    bucket_id = 'knowledge-bar-assets'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "kb_assets_insert" ON storage.objects
  FOR INSERT TO authenticated
  WITH CHECK (
    bucket_id = 'knowledge-bar-assets'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "kb_assets_update" ON storage.objects
  FOR UPDATE TO authenticated
  USING (
    bucket_id = 'knowledge-bar-assets'
    AND (storage.foldername(name))[1] = auth.uid()::text
  )
  WITH CHECK (
    bucket_id = 'knowledge-bar-assets'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

CREATE POLICY "kb_assets_delete" ON storage.objects
  FOR DELETE TO authenticated
  USING (
    bucket_id = 'knowledge-bar-assets'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- ============================================================
-- 8. Indexes (preserve multi-version, add useful lookups)
-- ============================================================

-- mind_maps: version unique constraint created in 002 — preserved
-- Additional lookup index for latest version queries
CREATE INDEX IF NOT EXISTS idx_mind_maps_kb_version_desc
  ON public.mind_maps (knowledge_base_id, version_no DESC);

CREATE INDEX IF NOT EXISTS idx_mind_maps_user_id
  ON public.mind_maps (user_id);

CREATE INDEX IF NOT EXISTS idx_generation_jobs_user_kb
  ON public.ai_generation_jobs (user_id, knowledge_base_id);

-- knowledge_bases user+updated already created in 001; skip if exists
CREATE INDEX IF NOT EXISTS idx_knowledge_bases_user_updated
  ON public.knowledge_bases (user_id, updated_at DESC);

-- ============================================================
-- 9. Content length constraint (defense in depth)
-- ============================================================

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE constraint_name = 'chk_content_md_length' AND table_name = 'knowledge_bases'
  ) THEN
    ALTER TABLE public.knowledge_bases
      ADD CONSTRAINT chk_content_md_length CHECK (length(content_md) <= 200000);
  END IF;
END $$;
