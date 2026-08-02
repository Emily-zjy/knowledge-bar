"""Pydantic models for the V0 mind map system."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SourceParagraph(BaseModel):
    id: str
    text: str
    order: int


class MindMapNode(BaseModel):
    id: str
    parent_id: str | None = None
    text: str = Field(max_length=80)
    level: int = Field(ge=0, le=6)
    order: int = Field(ge=0)
    side: Literal["left", "right"] | None = None
    source_ids: list[str] = Field(default_factory=list)


class MindMapDraft(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    map_type: Literal["auto", "knowledge", "process"] = "auto"
    nodes: list[MindMapNode]


class ValidationError(BaseModel):
    code: str
    message: str
    node_id: str | None = None


class ValidationWarning(BaseModel):
    code: str
    message: str
    node_id: str | None = None


class ValidationResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    errors: list[ValidationError] = Field(default_factory=list)
    warnings: list[ValidationWarning] = Field(default_factory=list)
    retry_count: int = 0


class RenderNode(BaseModel):
    id: str
    parent_id: str | None = None
    text: str
    level: int
    order: int
    side: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 180.0
    height: float = 60.0


class RenderEdge(BaseModel):
    id: str
    source: str
    target: str


class RenderData(BaseModel):
    nodes: list[RenderNode]
    edges: list[RenderEdge]


class MindMapState(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "validating", "succeeded", "failed"] = "pending"
    title: str = ""
    raw_text: str = ""
    paragraphs: list[SourceParagraph] = Field(default_factory=list)
    draft: MindMapDraft | None = None
    validation: ValidationResult | None = None
    render_data: RenderData | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


# --- API Request/Response Models ---

class GenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200_000)
    title: str | None = Field(default=None, max_length=120)
    max_depth: int = Field(default=4, ge=2, le=6)
    source_only: bool = True
    map_type: Literal["auto", "knowledge", "process"] = "auto"


class GenerateResponse(BaseModel):
    task_id: str
    status: str
    title: str
    nodes: list[RenderNode]
    edges: list[RenderEdge]
    validation: ValidationResult | None = None
    created_at: str


class MindMapListItem(BaseModel):
    task_id: str
    title: str
    status: str
    node_count: int
    created_at: str
    updated_at: str


class PatchRequest(BaseModel):
    title: str | None = None
    update_node: dict | None = None
    delete_node_id: str | None = None
    move_node: dict | None = None


class RegenerateRequest(BaseModel):
    max_depth: int = Field(default=4, ge=2, le=6)
    map_type: Literal["auto", "knowledge", "process"] = "auto"
