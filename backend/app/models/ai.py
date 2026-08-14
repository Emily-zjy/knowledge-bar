from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field


class ApiError(BaseModel):
    code: str
    message: str


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: T | None = None
    error: ApiError | None = None


class GenerateMindMapRequest(BaseModel):
    knowledge_base_id: UUID | str
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    content_md: str = Field(min_length=1, max_length=120_000)
    requested_max_depth: int = Field(default=5, ge=3, le=6)


class MindMapNode(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    parentId: str | None = None
    text: str = Field(min_length=1, max_length=120)
    order: int = Field(ge=0)


class MindMapData(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    nodes: list[MindMapNode] = Field(min_length=1, max_length=25)


class GenerationMetadata(BaseModel):
    input_length: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    retry_count: int = 0
    schema_repair_count: int = 0
    latency_ms: int = 0
    node_count: int = 0
    tree_depth: int = 0
    prompt_version: str | None = None


class GenerateMindMapResult(BaseModel):
    generation_id: str
    status: Literal["succeeded"]
    mind_map: MindMapData
    metadata: GenerationMetadata | None = None


class ExportWordRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    markdown: str = Field(default="", max_length=5_000_000)
    knowledge_base_id: UUID | str | None = None


class GenerationJobResponse(BaseModel):
    id: str
    knowledge_base_id: str
    status: str
    error_code: str | None = None
    error_message: str | None = None
    model_name: str | None = None
    prompt_version: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class LatestMindMapResponse(BaseModel):
    id: str = ""
    knowledge_base_id: str
    version_no: int
    mind_map: MindMapData
    markdown: str = ""
    updated_at: str | None = None


class MindMapVersionItem(BaseModel):
    id: str
    version_no: int
    updated_at: str | None = None


class MindMapVersionsResponse(BaseModel):
    knowledge_base_id: str
    versions: list[MindMapVersionItem] = []


class NodeUpdate(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    text: str = Field(min_length=1, max_length=120)


class PatchMindMapRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    update_node: NodeUpdate | None = None


class RegenerateMindMapRequest(BaseModel):
    requested_max_depth: int = Field(default=5, ge=3, le=6)


class SupabaseRow(BaseModel):
    data: dict[str, Any]
