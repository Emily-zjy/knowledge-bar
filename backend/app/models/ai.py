from typing import Generic, Literal, TypeVar
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


class MindMapNode(BaseModel):
    id: str
    parentId: str | None = None
    text: str = Field(min_length=1, max_length=120)
    order: int = Field(ge=0)


class MindMapData(BaseModel):
    title: str
    nodes: list[MindMapNode]


class GenerateMindMapResult(BaseModel):
    generation_id: str
    status: Literal["succeeded"]
    mind_map: MindMapData


class ExportWordRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    markdown: str = Field(default="", max_length=120_000)
