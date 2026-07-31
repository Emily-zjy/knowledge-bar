"""Mind map API endpoints - V0 with SQLite persistence."""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, Header, HTTPException

from app.db import store as db
from app.models.mindmap import (
    GenerateRequest,
    GenerateResponse,
    MindMapDraft,
    MindMapListItem,
    MindMapState,
    PatchRequest,
    RenderData,
    RegenerateRequest,
)
from app.services.actions import render_mindmap, validate_mindmap
from app.services.auth import verify_optional_supabase_jwt
from app.services.mindmap_agent import generate_mindmap_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mindmaps", tags=["mindmaps"])


def _get_user_id(authorization: str | None) -> str | None:
    try:
        return verify_optional_supabase_jwt(authorization)
    except Exception:
        return None


def _state_to_response(state: MindMapState) -> GenerateResponse:
    nodes = state.render_data.nodes if state.render_data else []
    edges = state.render_data.edges if state.render_data else []
    return GenerateResponse(
        task_id=state.task_id,
        status=state.status,
        title=state.title,
        nodes=nodes,
        edges=edges,
        validation=state.validation,
        created_at=state.created_at.isoformat(),
    )


def _persist_state(state: MindMapState, user_id: str | None, request: GenerateRequest) -> None:
    db.save(
        task_id=state.task_id,
        user_id=user_id,
        title=state.title,
        status=state.status,
        raw_text=state.raw_text,
        generation_params={"max_depth": request.max_depth, "map_type": request.map_type},
        draft_json=state.draft.model_dump() if state.draft else None,
        render_json=state.render_data.model_dump() if state.render_data else None,
        validation_json=state.validation.model_dump() if state.validation else None,
        error_message=state.error_message,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


def _db_row_to_response(row: dict) -> GenerateResponse:
    render = row.get("render_json")
    nodes = render["nodes"] if render else []
    edges = render["edges"] if render else []
    validation = row.get("validation_json")
    from app.models.mindmap import ValidationResult, RenderNode, RenderEdge
    return GenerateResponse(
        task_id=row["task_id"],
        status=row["status"],
        title=row["title"],
        nodes=[RenderNode(**n) for n in nodes],
        edges=[RenderEdge(**e) for e in edges],
        validation=ValidationResult(**validation) if validation else None,
        created_at=row["created_at"],
    )


@router.post("/generate", response_model=GenerateResponse)
def generate(
    payload: GenerateRequest,
    authorization: str | None = Header(default=None),
) -> GenerateResponse:
    """Generate a mind map from text input."""
    user_id = _get_user_id(authorization)
    state = generate_mindmap_pipeline(payload)
    _persist_state(state, user_id, payload)
    return _state_to_response(state)


@router.get("/{task_id}", response_model=GenerateResponse)
def get_mindmap(task_id: str) -> GenerateResponse:
    """Retrieve a previously generated mind map by task_id."""
    row = db.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mind map not found")
    return _db_row_to_response(row)


@router.post("/{task_id}/regenerate", response_model=GenerateResponse)
def regenerate(
    task_id: str,
    payload: RegenerateRequest,
    authorization: str | None = Header(default=None),
) -> GenerateResponse:
    """Regenerate a mind map from its stored original text."""
    row = db.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mind map not found")

    user_id = _get_user_id(authorization)
    new_request = GenerateRequest(
        text=row["raw_text"],
        title=row["title"],
        max_depth=payload.max_depth,
        map_type=payload.map_type,
    )
    state = generate_mindmap_pipeline(new_request)
    _persist_state(state, user_id, new_request)
    return _state_to_response(state)


@router.patch("/{task_id}", response_model=GenerateResponse)
def patch_mindmap(
    task_id: str,
    payload: PatchRequest,
    authorization: str | None = Header(default=None),
) -> GenerateResponse:
    """Modify an existing mind map (title, node text, delete node, move node)."""
    row = db.get(task_id)
    if not row:
        raise HTTPException(status_code=404, detail="Mind map not found")

    draft_data = row.get("draft_json")
    if not draft_data:
        raise HTTPException(status_code=400, detail="No draft available to patch")

    if payload.title is not None:
        draft_data["title"] = payload.title

    if payload.update_node:
        node_id = payload.update_node.get("id")
        new_text = payload.update_node.get("text")
        if node_id and new_text:
            for node in draft_data["nodes"]:
                if node["id"] == node_id:
                    node["text"] = new_text[:80]
                    break

    if payload.delete_node_id:
        target_id = payload.delete_node_id
        to_delete = {target_id}
        changed = True
        while changed:
            changed = False
            for node in draft_data["nodes"]:
                if node["parent_id"] in to_delete and node["id"] not in to_delete:
                    to_delete.add(node["id"])
                    changed = True
        draft_data["nodes"] = [n for n in draft_data["nodes"] if n["id"] not in to_delete]

    if payload.move_node:
        node_id = payload.move_node.get("id")
        new_parent_id = payload.move_node.get("new_parent_id")
        if node_id and new_parent_id:
            for node in draft_data["nodes"]:
                if node["id"] == node_id:
                    node["parent_id"] = new_parent_id
                    break

    render_result = render_mindmap(draft_data)
    title = draft_data.get("title", row["title"])
    now = datetime.utcnow()
    db.update_draft_and_render(task_id, title, draft_data, render_result, now)

    return _db_row_to_response(db.get(task_id))


@router.get("", response_model=list[MindMapListItem])
def list_mindmaps(
    authorization: str | None = Header(default=None),
) -> list[MindMapListItem]:
    """List all generated mind maps for the current session."""
    user_id = _get_user_id(authorization)
    rows = db.list_by_user(user_id)
    items = []
    for row in rows:
        draft = row.get("draft_json")
        node_count = len(draft["nodes"]) if draft else 0
        items.append(MindMapListItem(
            task_id=row["task_id"],
            title=row["title"],
            status=row["status"],
            node_count=node_count,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        ))
    return items
