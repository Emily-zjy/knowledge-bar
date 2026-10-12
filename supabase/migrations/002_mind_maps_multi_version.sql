-- Migration 002: Switch mind_maps from single-row-per-KB to multi-version-per-KB.
--
-- Before: UNIQUE(user_id, knowledge_base_id) forced one row per user per KB.
-- After:  UNIQUE(user_id, knowledge_base_id, version_no) allows history;
--         backend always INSERTs with version_no = max + 1.
--
-- Existing data is compatible: all rows have version_no = 1, so the new
-- constraint does not conflict.

DROP INDEX IF EXISTS public.mind_maps_one_latest_per_base;

CREATE UNIQUE INDEX IF NOT EXISTS mind_maps_version_unique
  ON public.mind_maps(user_id, knowledge_base_id, version_no);

CREATE INDEX IF NOT EXISTS mind_maps_latest_lookup
  ON public.mind_maps(user_id, knowledge_base_id, version_no DESC);
