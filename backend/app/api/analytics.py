from __future__ import annotations

import logging

from fastapi import APIRouter, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from uuid import UUID

from app.models.ai import ApiResponse, ApiError
from app.services.auth import AuthError, verify_required_supabase_jwt
from app.services.supabase_store import SupabaseStoreError, supabase_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

ALLOWED_EVENTS = frozenset([
    "mindmap_generate_clicked",
    "mindmap_regenerated",
    "mindmap_node_edited",
    "mindmap_node_added",
    "mindmap_node_deleted",
    "mindmap_node_reparented",
    "mindmap_feedback_submitted",
    "mindmap_saved",
    "mindmap_exported",
])


class AnalyticsEvent(BaseModel):
    session_id: UUID
    event_name: str = Field(min_length=1, max_length=100)
    knowledge_base_id: UUID | None = None
    generation_id: UUID | None = None
    mind_map_id: UUID | None = None
    client_event_id: UUID
    properties: dict | None = None


class AnalyticsEventsRequest(BaseModel):
    events: list[AnalyticsEvent] = Field(min_length=1, max_length=50)


class AnalyticsEventsResponse(BaseModel):
    accepted: int = 0
    duplicates: int = 0


def _api_error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=ApiResponse(success=False, error=ApiError(code=code, message=message)).model_dump(),
    )


@router.post("/events", response_model=None)
def ingest_events(
    body: AnalyticsEventsRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse[AnalyticsEventsResponse] | JSONResponse:
    try:
        user_id = verify_required_supabase_jwt(authorization)
    except AuthError as exc:
        return _api_error(401, exc.code, exc.message)

    accepted = 0
    duplicates = 0

    for event in body.events:
        if event.event_name not in ALLOWED_EVENTS:
            return _api_error(422, "INVALID_EVENT_NAME", f"Event name '{event.event_name}' is not allowed.")

        if event.generation_id:
            try:
                supabase_store.get_generation_job_for_user(str(event.generation_id), user_id)
            except SupabaseStoreError:
                continue

        if event.knowledge_base_id:
            try:
                supabase_store.get_knowledge_base_for_user(str(event.knowledge_base_id), user_id)
            except SupabaseStoreError:
                continue

        safe_props = _sanitize_properties(event.properties)

        row = {
            "user_id": user_id,
            "session_id": str(event.session_id),
            "event_name": event.event_name,
            "knowledge_base_id": str(event.knowledge_base_id) if event.knowledge_base_id else None,
            "generation_id": str(event.generation_id) if event.generation_id else None,
            "mind_map_id": str(event.mind_map_id) if event.mind_map_id else None,
            "client_event_id": str(event.client_event_id),
            "properties": safe_props,
        }

        try:
            supabase_store.insert_analytics_event(row)
            accepted += 1
        except SupabaseStoreError as exc:
            if "duplicate" in (exc.message or "").lower() or "unique" in (exc.message or "").lower():
                duplicates += 1
            else:
                logger.warning("analytics_insert_failed", extra={"error": exc.message, "event": event.event_name})

    return ApiResponse(success=True, data=AnalyticsEventsResponse(accepted=accepted, duplicates=duplicates))


def _sanitize_properties(props: dict | None) -> dict:
    if not props:
        return {}
    sanitized = {}
    for key, value in props.items():
        if isinstance(value, str) and len(value) > 500:
            sanitized[key] = value[:500]
        else:
            sanitized[key] = value
    return sanitized
