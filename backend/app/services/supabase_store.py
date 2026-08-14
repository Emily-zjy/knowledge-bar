from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models.ai import MindMapData

logger = logging.getLogger(__name__)

MAX_VERSION_RETRIES = 3


class SupabaseStoreError(RuntimeError):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_list(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


class SupabaseStore:
    def __init__(self) -> None:
        self.base_url = (settings.supabase_url or "").rstrip("/")
        self.service_key = settings.supabase_secret_key or settings.supabase_service_role_key

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.service_key)

    def _ensure_configured(self) -> None:
        if not self.configured:
            raise SupabaseStoreError(
                503,
                "SUPABASE_NOT_CONFIGURED",
                "Supabase is not configured on the backend.",
            )

    def _headers(self, prefer: str | None = None) -> dict[str, str]:
        self._ensure_configured()
        key = self.service_key or ""
        headers: dict[str, str] = {
            "apikey": key,
            "Content-Type": "application/json",
        }
        if not key.startswith("sb_secret_"):
            headers["Authorization"] = f"Bearer {key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(
        self,
        method: str,
        table: str,
        *,
        params: dict[str, str] | None = None,
        json_body: Any | None = None,
        prefer: str | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> Any:
        self._ensure_configured()
        url = f"{self.base_url}/rest/v1/{table}"
        with httpx.Client(timeout=20) as client:
            response = client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=self._headers(prefer),
            )

        if response.status_code not in expected:
            raise SupabaseStoreError(
                response.status_code if response.status_code in (409, 404, 401, 403) else 502,
                "SUPABASE_REST_ERROR",
                f"Supabase REST request failed with HTTP {response.status_code}.",
            )
        if response.status_code == 204 or not response.content:
            return None
        return response.json()

    def get_knowledge_base_for_user(self, knowledge_base_id: str, user_id: str) -> dict[str, Any]:
        rows = _as_list(
            self._request(
                "GET",
                "knowledge_bases",
                params={
                    "select": "id,user_id,name,description,content_md,updated_at",
                    "id": f"eq.{knowledge_base_id}",
                    "user_id": f"eq.{user_id}",
                    "limit": "1",
                },
            ),
        )
        if not rows:
            raise SupabaseStoreError(404, "KNOWLEDGE_BASE_NOT_FOUND", "Knowledge base was not found.")
        return rows[0]

    def update_knowledge_base_content(self, knowledge_base_id: str, user_id: str, content_md: str) -> None:
        self._request(
            "PATCH",
            "knowledge_bases",
            params={
                "id": f"eq.{knowledge_base_id}",
                "user_id": f"eq.{user_id}",
            },
            json_body={"content_md": content_md, "updated_at": _now_iso()},
            expected=(200, 204),
        )

    def create_generation_job(self, user_id: str, knowledge_base_id: str, status: str = "running") -> dict[str, Any]:
        job = {
            "id": str(uuid4()),
            "user_id": user_id,
            "knowledge_base_id": knowledge_base_id,
            "status": status,
            "model_name": settings.ai_model,
            "prompt_version": settings.ai_prompt_version,
            "started_at": _now_iso() if status == "running" else None,
        }
        rows = _as_list(
            self._request(
                "POST",
                "ai_generation_jobs",
                json_body=job,
                prefer="return=representation",
                expected=(201,),
            ),
        )
        return rows[0] if rows else job

    def update_generation_job(
        self,
        job_id: str,
        user_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        input_length: int | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        retry_count: int | None = None,
        schema_repair_count: int | None = None,
        latency_ms: int | None = None,
        node_count: int | None = None,
        tree_depth: int | None = None,
        prompt_version: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "status": status,
            "error_code": error_code,
            "error_message": error_message,
            "finished_at": _now_iso() if status in {"succeeded", "failed"} else None,
            "updated_at": _now_iso(),
        }
        if input_length is not None:
            payload["input_length"] = input_length
        if input_tokens is not None:
            payload["input_tokens"] = input_tokens
        if output_tokens is not None:
            payload["output_tokens"] = output_tokens
        if retry_count is not None:
            payload["retry_count"] = retry_count
        if schema_repair_count is not None:
            payload["schema_repair_count"] = schema_repair_count
        if latency_ms is not None:
            payload["latency_ms"] = latency_ms
        if node_count is not None:
            payload["node_count"] = node_count
        if tree_depth is not None:
            payload["tree_depth"] = tree_depth
        if prompt_version is not None:
            payload["prompt_version"] = prompt_version
        self._request(
            "PATCH",
            "ai_generation_jobs",
            params={"id": f"eq.{job_id}", "user_id": f"eq.{user_id}"},
            json_body=payload,
            prefer="return=minimal",
            expected=(204,),
        )

    def get_generation_job_for_user(self, job_id: str, user_id: str) -> dict[str, Any]:
        rows = _as_list(
            self._request(
                "GET",
                "ai_generation_jobs",
                params={"select": "*", "id": f"eq.{job_id}", "user_id": f"eq.{user_id}", "limit": "1"},
            ),
        )
        if not rows:
            raise SupabaseStoreError(404, "JOB_NOT_FOUND", "Generation job was not found.")
        return rows[0]

    def get_latest_mind_map(self, knowledge_base_id: str, user_id: str) -> dict[str, Any]:
        rows = _as_list(
            self._request(
                "GET",
                "mind_maps",
                params={
                    "select": "id,user_id,knowledge_base_id,data_jsonb,markdown,version_no,updated_at",
                    "knowledge_base_id": f"eq.{knowledge_base_id}",
                    "user_id": f"eq.{user_id}",
                    "order": "version_no.desc",
                    "limit": "1",
                },
            ),
        )
        if not rows:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")
        return rows[0]

    def list_mind_map_versions(self, knowledge_base_id: str, user_id: str) -> list[dict[str, Any]]:
        rows = _as_list(
            self._request(
                "GET",
                "mind_maps",
                params={
                    "select": "id,version_no,updated_at",
                    "knowledge_base_id": f"eq.{knowledge_base_id}",
                    "user_id": f"eq.{user_id}",
                    "order": "version_no.desc",
                },
            ),
        )
        return rows

    def get_mind_map_by_id(self, mind_map_id: str, user_id: str) -> dict[str, Any]:
        rows = _as_list(
            self._request(
                "GET",
                "mind_maps",
                params={
                    "select": "id,user_id,knowledge_base_id,data_jsonb,markdown,version_no,updated_at",
                    "id": f"eq.{mind_map_id}",
                    "user_id": f"eq.{user_id}",
                    "limit": "1",
                },
            ),
        )
        if not rows:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")
        return rows[0]

    def patch_mind_map(self, mind_map_id: str, user_id: str, data_jsonb: dict, markdown: str) -> dict[str, Any]:
        payload = {
            "data_jsonb": data_jsonb,
            "markdown": markdown,
            "updated_at": _now_iso(),
        }
        self._request(
            "PATCH",
            "mind_maps",
            params={"id": f"eq.{mind_map_id}", "user_id": f"eq.{user_id}"},
            json_body=payload,
            prefer="return=minimal",
            expected=(204,),
        )
        return self.get_mind_map_by_id(mind_map_id, user_id)

    def delete_mind_map(self, mind_map_id: str, user_id: str) -> None:
        rows = _as_list(
            self._request(
                "GET",
                "mind_maps",
                params={
                    "select": "id",
                    "id": f"eq.{mind_map_id}",
                    "user_id": f"eq.{user_id}",
                    "limit": "1",
                },
            ),
        )
        if not rows:
            raise SupabaseStoreError(404, "MIND_MAP_NOT_FOUND", "Mind map was not found.")
        self._request(
            "DELETE",
            "mind_maps",
            params={"id": f"eq.{mind_map_id}", "user_id": f"eq.{user_id}"},
            expected=(200, 204),
        )

    def save_mind_map(
        self,
        *,
        user_id: str,
        knowledge_base_id: str,
        mind_map: MindMapData,
        markdown: str,
    ) -> dict[str, Any]:
        """Insert a new mind map version with retry on unique constraint conflict."""
        for attempt in range(MAX_VERSION_RETRIES):
            try:
                existing = self.get_latest_mind_map(knowledge_base_id, user_id)
                version_no = int(existing.get("version_no") or 0) + 1
            except SupabaseStoreError as exc:
                if exc.status_code != 404:
                    raise
                version_no = 1

            payload = {
                "id": str(uuid4()),
                "user_id": user_id,
                "knowledge_base_id": knowledge_base_id,
                "data_jsonb": mind_map.model_dump(),
                "markdown": markdown,
                "version_no": version_no,
            }
            try:
                rows = _as_list(
                    self._request(
                        "POST",
                        "mind_maps",
                        json_body=payload,
                        prefer="return=representation",
                        expected=(201,),
                    ),
                )
                return rows[0] if rows else payload
            except SupabaseStoreError as exc:
                is_conflict = exc.status_code == 409
                if is_conflict and attempt < MAX_VERSION_RETRIES - 1:
                    logger.warning("version_conflict_retry", extra={"attempt": attempt + 1, "version_no": version_no})
                    continue
                if not is_conflict:
                    raise
                raise

        raise SupabaseStoreError(409, "VERSION_CONFLICT", "Failed to save mind map after retries.")

    def insert_analytics_event(self, row: dict[str, Any]) -> None:
        self._request(
            "POST",
            "analytics_events",
            json_body=row,
            prefer="return=minimal",
            expected=(201,),
        )


supabase_store = SupabaseStore()
