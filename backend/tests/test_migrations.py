"""Static analysis tests for Supabase migration files (003 security hardening).

These tests read the SQL files and verify security properties via string assertions.
They do NOT connect to any database.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "supabase" / "migrations"

BUSINESS_TABLES = [
    "profiles",
    "knowledge_bases",
    "tags",
    "knowledge_base_tags",
    "attachments",
    "mind_maps",
    "ai_generation_jobs",
]


@pytest.fixture(scope="module")
def sql_001() -> str:
    return (MIGRATIONS_DIR / "001_initial_schema.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_002() -> str:
    return (MIGRATIONS_DIR / "002_mind_maps_multi_version.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_003() -> str:
    return (MIGRATIONS_DIR / "003_security_hardening.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sql_006() -> str:
    return (MIGRATIONS_DIR / "006_durable_ai_generation_queue.sql").read_text(encoding="utf-8")


class TestMigrationOrder:
    def test_001_creates_tables(self, sql_001):
        for table in BUSINESS_TABLES:
            assert f"public.{table}" in sql_001 or f'public."{table}"' in sql_001

    def test_002_drops_single_version_index(self, sql_002):
        assert "DROP INDEX IF EXISTS public.mind_maps_one_latest_per_base" in sql_002

    def test_002_creates_multi_version_unique(self, sql_002):
        assert "mind_maps_version_unique" in sql_002
        assert "user_id, knowledge_base_id, version_no" in sql_002

    def test_003_does_not_recreate_single_row_index(self, sql_003):
        assert "mind_maps_one_latest_per_base" not in sql_003


class TestRevokeGrants:
    def test_revoke_schema_usage_from_public_and_anon(self, sql_003):
        assert "REVOKE USAGE ON SCHEMA public FROM PUBLIC, anon" in sql_003

    def test_schema_usage_grant_only_authenticated_and_service_role(self, sql_003):
        assert "GRANT USAGE ON SCHEMA public TO authenticated, service_role" in sql_003

    def test_revoke_tables_from_public_and_anon(self, sql_003):
        assert "FROM PUBLIC, anon" in sql_003
        for table in BUSINESS_TABLES:
            assert f"public.{table}" in sql_003

    def test_profiles_authenticated_select_update_only(self, sql_003):
        assert "GRANT SELECT, UPDATE ON public.profiles TO authenticated" in sql_003
        # Must NOT have INSERT or DELETE for profiles
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON public.profiles" not in sql_003

    def test_authenticated_full_crud_on_data_tables(self, sql_003):
        for table in ["knowledge_bases", "tags", "knowledge_base_tags", "attachments"]:
            assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO authenticated" in sql_003

    def test_authenticated_select_only_on_backend_tables(self, sql_003):
        assert "GRANT SELECT ON public.mind_maps TO authenticated" in sql_003
        assert "GRANT SELECT ON public.ai_generation_jobs TO authenticated" in sql_003

    def test_service_role_full_crud(self, sql_003):
        assert "TO service_role" in sql_003
        assert "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE" in sql_003
        for table in BUSINESS_TABLES:
            assert f"public.{table}" in sql_003


class TestRLS:
    def test_all_tables_enable_rls(self, sql_003):
        for table in BUSINESS_TABLES:
            assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql_003

    def test_policies_use_to_authenticated(self, sql_003):
        # Every CREATE POLICY should have TO authenticated
        policies = re.findall(r"CREATE POLICY\s+\w+\s+ON\s+\S+.*?;", sql_003, re.DOTALL)
        for policy in policies:
            assert "TO authenticated" in policy, f"Policy missing TO authenticated: {policy[:80]}"

    def test_update_policies_have_using_and_with_check(self, sql_003):
        # Find all UPDATE policies
        update_policies = re.findall(
            r"CREATE POLICY\s+\w+\s+ON\s+\S+\s+FOR UPDATE.*?;",
            sql_003,
            re.DOTALL | re.IGNORECASE,
        )
        for policy in update_policies:
            assert "USING" in policy, f"UPDATE policy missing USING: {policy[:80]}"
            assert "WITH CHECK" in policy, f"UPDATE policy missing WITH CHECK: {policy[:80]}"


class TestCrossTableOwnership:
    def test_kbt_insert_checks_kb_and_tag_ownership(self, sql_003):
        # Find the kbt_insert policy
        match = re.search(r"CREATE POLICY kbt_insert.*?;", sql_003, re.DOTALL)
        assert match, "kbt_insert policy not found"
        policy = match.group(0)
        assert "knowledge_bases" in policy, "kbt_insert must verify KB ownership"
        assert "tags" in policy, "kbt_insert must verify tag ownership"

    def test_att_insert_checks_kb_ownership(self, sql_003):
        match = re.search(r"CREATE POLICY att_insert.*?;", sql_003, re.DOTALL)
        assert match, "att_insert policy not found"
        policy = match.group(0)
        assert "knowledge_bases" in policy, "att_insert must verify KB ownership"

    def test_mm_select_checks_kb_ownership(self, sql_003):
        match = re.search(r"CREATE POLICY mm_select.*?;", sql_003, re.DOTALL)
        assert match, "mm_select policy not found"
        policy = match.group(0)
        assert "knowledge_bases" in policy, "mm_select must verify KB ownership"

    def test_gj_select_checks_kb_ownership(self, sql_003):
        match = re.search(r"CREATE POLICY gj_select.*?;", sql_003, re.DOTALL)
        assert match, "gj_select policy not found"
        policy = match.group(0)
        assert "knowledge_bases" in policy, "gj_select must verify KB ownership"


class TestProfileTrigger:
    def test_trigger_function_exists(self, sql_003):
        assert "handle_new_user()" in sql_003

    def test_trigger_on_auth_users(self, sql_003):
        assert "AFTER INSERT ON auth.users" in sql_003

    def test_backfill_exists(self, sql_003):
        assert "FROM auth.users" in sql_003
        assert "ON CONFLICT (id) DO NOTHING" in sql_003

    def test_security_definer(self, sql_003):
        assert "SECURITY DEFINER" in sql_003

    def test_search_path_set(self, sql_003):
        assert "SET search_path = ''" in sql_003

    def test_execute_revoked(self, sql_003):
        assert "REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC" in sql_003
        assert "REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon" in sql_003
        assert "REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM authenticated" in sql_003


class TestStorage:
    def test_bucket_private(self, sql_003):
        assert "public = false" in sql_003

    def test_storage_select_policy(self, sql_003):
        match = re.search(r'CREATE POLICY "kb_assets_select".*?;', sql_003, re.DOTALL)
        assert match, "Storage SELECT policy missing"
        assert "TO authenticated" in match.group(0)
        assert "auth.uid()::text" in match.group(0)

    def test_storage_insert_policy(self, sql_003):
        match = re.search(r'CREATE POLICY "kb_assets_insert".*?;', sql_003, re.DOTALL)
        assert match, "Storage INSERT policy missing"
        assert "TO authenticated" in match.group(0)
        assert "WITH CHECK" in match.group(0)

    def test_storage_update_policy(self, sql_003):
        match = re.search(r'CREATE POLICY "kb_assets_update".*?;', sql_003, re.DOTALL)
        assert match, "Storage UPDATE policy missing"
        assert "USING" in match.group(0)
        assert "WITH CHECK" in match.group(0)
        assert "TO authenticated" in match.group(0)

    def test_storage_delete_policy(self, sql_003):
        match = re.search(r'CREATE POLICY "kb_assets_delete".*?;', sql_003, re.DOTALL)
        assert match, "Storage DELETE policy missing"
        assert "TO authenticated" in match.group(0)

    def test_no_anon_storage_policy(self, sql_003):
        # Ensure no storage policy grants to anon
        storage_policies = re.findall(r'CREATE POLICY "kb_assets_\w+".*?;', sql_003, re.DOTALL)
        for policy in storage_policies:
            assert "TO anon" not in policy


class TestSetUpdatedAt:
    def test_function_has_search_path(self, sql_003):
        match = re.search(r"CREATE OR REPLACE FUNCTION public\.set_updated_at\(\).*?;", sql_003, re.DOTALL)
        assert match, "set_updated_at function not found in 003"
        assert "SET search_path = ''" in match.group(0)

    def test_function_no_security_definer(self, sql_003):
        match = re.search(
            r"CREATE OR REPLACE FUNCTION public\.set_updated_at\(\).*?\$\$",
            sql_003,
            re.DOTALL,
        )
        assert match, "set_updated_at function not found"
        assert "SECURITY DEFINER" not in match.group(0)

    def test_revoke_from_anon(self, sql_003):
        assert "REVOKE EXECUTE ON FUNCTION public.set_updated_at() FROM anon" in sql_003


class TestMultiVersionIndex:
    def test_002_unique_index_preserved(self, sql_002):
        assert "mind_maps_version_unique" in sql_002
        assert "user_id, knowledge_base_id, version_no" in sql_002

    def test_003_does_not_drop_version_unique(self, sql_003):
        assert "DROP" not in sql_003 or "mind_maps_version_unique" not in sql_003

    def test_003_has_latest_lookup_index(self, sql_003):
        assert "idx_mind_maps_kb_version_desc" in sql_003
        assert "version_no DESC" in sql_003


class TestDurableGenerationQueueMigration:
    def test_adds_durable_job_snapshot_and_lease_columns(self, sql_006):
        for column in [
            "operation",
            "client_request_id",
            "request_payload",
            "queued_at",
            "lease_expires_at",
            "heartbeat_at",
            "worker_id",
            "claim_count",
            "result_mind_map_id",
        ]:
            assert f"ADD COLUMN IF NOT EXISTS {column}" in sql_006

    def test_queue_has_atomic_rpc_security_and_fifo_claim(self, sql_006):
        assert "enqueue_ai_generation_job" in sql_006
        assert "recover_stale_ai_jobs" in sql_006
        assert "claim_ai_generation_jobs" in sql_006
        assert "p_global_limit integer" in sql_006
        assert "p_claim_limit integer" in sql_006
        assert "(p_request_payload->>'requested_max_depth')::integer" in sql_006
        assert sql_006.count("repair_attempted = coalesce") == 2
        assert sql_006.count("repair_success = coalesce") == 2
        assert "FOR UPDATE SKIP LOCKED" in sql_006
        assert "pg_advisory_xact_lock" in sql_006
        assert "SECURITY INVOKER" in sql_006
        assert "SET search_path = public" in sql_006
        assert "LEGACY_JOB_NOT_EXECUTED" in sql_006
        assert "WHERE status IN ('pending', 'running')" in sql_006

    def test_queue_functions_are_not_publicly_callable(self, sql_006):
        assert "FROM PUBLIC, anon, authenticated" in sql_006
        assert "TO service_role" in sql_006

    def test_idempotency_and_single_result_indexes_exist(self, sql_006):
        assert "ai_generation_jobs_request_id_unique" in sql_006
        assert "mind_maps_generation_job_unique" in sql_006
        assert sql_006.count("queue_wait_ms = coalesce") == 1
        assert "WHERE id = p_job_id\n  FOR UPDATE;" in sql_006
        assert "generation_job_id" in sql_006

    def test_no_credentials_or_content_headers_in_snapshot(self, sql_006):
        assert "authorization" not in sql_006.lower()
        assert "api_key" not in sql_006.lower()
