from __future__ import annotations

import base64
import binascii
import logging
import re
import time
from collections import defaultdict
from io import BytesIO
from urllib.parse import quote

from docx import Document
from docx.shared import Inches
from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from app.core.config import settings
from app.models.ai import (
    ApiError,
    ApiResponse,
    ExportWordRequest,
    GenerateMindMapRequest,
    GenerateMindMapResult,
    GenerationJobResponse,
    GuestGenerateRequest,
    LatestMindMapResponse,
    MindMapData,
)
from app.services.ai_mindmap import MindMapGenerationError, generate_mind_map
from app.services.auth import AuthError, verify_required_supabase_jwt
from app.services.supabase_store import SupabaseStoreError, supabase_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])
IMAGE_MARKDOWN_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)(?:\{width=(\d+)\})?")

GUEST_RATE_WINDOW = 600  # 10 minutes
GUEST_RATE_LIMIT = 5  # max requests per window per IP
_guest_requests: dict[str, list[float]] = defaultdict(list)


def _check_guest_rate_limit(client_ip: str) -> bool:
    now = time.time()
    window = _guest_requests[client_ip]
    window[:] = [t for t in window if now - t < GUEST_RATE_WINDOW]
    if len(window) >= GUEST_RATE_LIMIT:
        return False
    window.append(now)
    return True


def _api_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ApiResponse(success=False, error=ApiError(code=code, message=message)).model_dump(),
    )


def mind_map_to_markdown(mind_map: MindMapData) -> str:
    children_by_parent: dict[str | None, list] = {}
    for node in mind_map.nodes:
        children_by_parent.setdefault(node.parentId, []).append(node)
    for siblings in children_by_parent.values():
        siblings.sort(key=lambda node: node.order)

    lines: list[str] = []

    def render(parent_id: str | None, level: int) -> None:
        for node in children_by_parent.get(parent_id, []):
            if level == 0:
                lines.append(f"# {node.text}")
            else:
                lines.append(f"{'  ' * max(level - 1, 0)}- {node.text}")
            render(node.id, level + 1)

    render(None, 0)
    return "\n".join(lines)


def _add_markdown_image(document: Document, alt: str, src: str, width: str | None = None) -> bool:
    if not src.startswith("data:image/"):
        return False

    try:
        _, encoded = src.split(",", 1)
        image_bytes = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        return False

    width_inches = None
    if width:
        try:
            width_pixels = min(max(int(width), 80), 640)
            width_inches = Inches(width_pixels / 96)
        except ValueError:
            width_inches = None

    paragraph = document.add_paragraph()
    run = paragraph.add_run()
    run.add_picture(BytesIO(image_bytes), width=width_inches)
    if alt:
        document.add_paragraph(alt)
    return True


def _add_markdown_line(document: Document, line: str) -> None:
    remaining = line
    while True:
        match = IMAGE_MARKDOWN_PATTERN.search(remaining)
        if not match:
            break

        prefix = remaining[: match.start()].strip()
        if prefix:
            document.add_paragraph(prefix)

        alt, src, width = match.group(1), match.group(2), match.group(3)
        if not _add_markdown_image(document, alt, src, width):
            document.add_paragraph(alt or "image")

        remaining = remaining[match.end() :]

    if remaining.strip():
        document.add_paragraph(remaining.strip())


def _word_stream(title: str, markdown: str) -> StreamingResponse:
    document = Document()
    document.add_heading(title, level=1)

    if markdown.strip():
        for raw_line in markdown.splitlines():
            line = raw_line.rstrip()
            if not line:
                document.add_paragraph("")
            elif line.startswith("# "):
                document.add_heading(line[2:].strip(), level=1)
            elif line.startswith("## "):
                document.add_heading(line[3:].strip(), level=2)
            elif line.lstrip().startswith("- "):
                document.add_paragraph(line.lstrip()[2:].strip(), style="List Bullet")
            else:
                _add_markdown_line(document, line)
    else:
        document.add_paragraph("No content.")

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    filename = quote(f"{title}.docx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/mindmap/generate", response_model=None)
def generate_mindmap(
    payload: GenerateMindMapRequest,
    authorization: str | None = Header(default=None),
) -> ApiResponse[GenerateMindMapResult] | JSONResponse:
    job_id: str | None = None
    user_id: str | None = None
    try:
        user_id = verify_required_supabase_jwt(authorization)
        kb = supabase_store.get_knowledge_base_for_user(str(payload.knowledge_base_id), user_id)
        content_md = payload.content_md.strip() or str(kb.get("content_md") or "").strip()
        if not content_md:
            return _api_error(422, "EMPTY_CONTENT", "Knowledge content cannot be empty.")

        job = supabase_store.create_generation_job(user_id, str(payload.knowledge_base_id), "running")
        job_id = str(job["id"])
        generation_payload = payload.model_copy(
            update={
                "title": str(kb.get("name") or payload.title),
                "description": str(kb.get("description") or payload.description or ""),
                "content_md": content_md,
            },
        )
        result = generate_mind_map(payload=generation_payload, authorization=authorization, guest_session_id=None)
        result.generation_id = job_id
        markdown = mind_map_to_markdown(result.mind_map)
        supabase_store.save_mind_map(
            user_id=user_id,
            knowledge_base_id=str(payload.knowledge_base_id),
            mind_map=result.mind_map,
            markdown=markdown,
        )
        supabase_store.update_generation_job(job_id, user_id, status="succeeded")
        return ApiResponse(success=True, data=result)
    except AuthError as exc:
        status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
        return _api_error(status, exc.code, exc.message)
    except SupabaseStoreError as exc:
        return _api_error(exc.status_code, exc.code, exc.message)
    except MindMapGenerationError as exc:
        if job_id and user_id:
            try:
                supabase_store.update_generation_job(
                    job_id,
                    user_id,
                    status="failed",
                    error_code=exc.code,
                    error_message=exc.message,
                )
            except SupabaseStoreError:
                logger.exception("failed_to_update_generation_job")
        return _api_error(502, exc.code, exc.message)


@router.post("/mindmap/generate-guest", response_model=None)
def generate_mindmap_guest(
    payload: GuestGenerateRequest,
    request: Request,
) -> ApiResponse[GenerateMindMapResult] | JSONResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not _check_guest_rate_limit(client_ip):
        return _api_error(429, "RATE_LIMITED", "Too many requests. Please try again later.")

    generation_payload = GenerateMindMapRequest(
        knowledge_base_id="00000000-0000-0000-0000-000000000000",
        title=payload.title,
        description=payload.description,
        content_md=payload.content_md,
    )
    try:
        result = generate_mind_map(payload=generation_payload, authorization=None, guest_session_id=client_ip)
        return ApiResponse(success=True, data=result)
    except MindMapGenerationError as exc:
        return _api_error(502, exc.code, exc.message)


@router.get("/mindmap/jobs/{job_id}", response_model=None)
def get_generation_job(
    job_id: str,
    authorization: str | None = Header(default=None),
) -> ApiResponse[GenerationJobResponse] | JSONResponse:
    try:
        user_id = verify_required_supabase_jwt(authorization)
        row = supabase_store.get_generation_job_for_user(job_id, user_id)
        return ApiResponse(success=True, data=GenerationJobResponse(**row))
    except AuthError as exc:
        status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
        return _api_error(status, exc.code, exc.message)
    except SupabaseStoreError as exc:
        return _api_error(exc.status_code, exc.code, exc.message)


@router.get("/mindmap/latest/{knowledge_base_id}", response_model=None)
def get_latest_mind_map(
    knowledge_base_id: str,
    authorization: str | None = Header(default=None),
) -> ApiResponse[LatestMindMapResponse] | JSONResponse:
    try:
        user_id = verify_required_supabase_jwt(authorization)
        supabase_store.get_knowledge_base_for_user(knowledge_base_id, user_id)
        row = supabase_store.get_latest_mind_map(knowledge_base_id, user_id)
        data = MindMapData.model_validate(row["data_jsonb"])
        return ApiResponse(
            success=True,
            data=LatestMindMapResponse(
                knowledge_base_id=knowledge_base_id,
                version_no=int(row.get("version_no") or 1),
                mind_map=data,
                markdown=str(row.get("markdown") or ""),
                updated_at=row.get("updated_at"),
            ),
        )
    except AuthError as exc:
        status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
        return _api_error(status, exc.code, exc.message)
    except SupabaseStoreError as exc:
        return _api_error(exc.status_code, exc.code, exc.message)


@router.get("/export/markdown/{knowledge_base_id}", response_model=None)
def export_markdown(
    knowledge_base_id: str,
    authorization: str | None = Header(default=None),
) -> PlainTextResponse | JSONResponse:
    try:
        user_id = verify_required_supabase_jwt(authorization)
        kb = supabase_store.get_knowledge_base_for_user(knowledge_base_id, user_id)
        try:
            latest = supabase_store.get_latest_mind_map(knowledge_base_id, user_id)
            markdown = str(latest.get("markdown") or "") or mind_map_to_markdown(MindMapData.model_validate(latest["data_jsonb"]))
        except SupabaseStoreError as exc:
            if exc.status_code != 404:
                raise
            markdown = str(kb.get("content_md") or "")
        filename = quote(f"{kb.get('name') or 'knowledge-bar'}.md")
        return PlainTextResponse(
            markdown,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
        )
    except AuthError as exc:
        status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
        return _api_error(status, exc.code, exc.message)
    except SupabaseStoreError as exc:
        return _api_error(exc.status_code, exc.code, exc.message)


@router.get("/export/word/{knowledge_base_id}", response_model=None)
def export_word_from_knowledge_base(
    knowledge_base_id: str,
    authorization: str | None = Header(default=None),
) -> StreamingResponse | JSONResponse:
    try:
        user_id = verify_required_supabase_jwt(authorization)
        kb = supabase_store.get_knowledge_base_for_user(knowledge_base_id, user_id)
        try:
            latest = supabase_store.get_latest_mind_map(knowledge_base_id, user_id)
            markdown = str(latest.get("markdown") or "") or mind_map_to_markdown(MindMapData.model_validate(latest["data_jsonb"]))
        except SupabaseStoreError as exc:
            if exc.status_code != 404:
                raise
            markdown = str(kb.get("content_md") or "")
        return _word_stream(str(kb.get("name") or "Knowledge Bar"), markdown)
    except AuthError as exc:
        status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
        return _api_error(status, exc.code, exc.message)
    except SupabaseStoreError as exc:
        return _api_error(exc.status_code, exc.code, exc.message)


@router.post("/export/word", response_model=None)
def export_word(
    payload: ExportWordRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse | JSONResponse:
    if payload.knowledge_base_id:
        try:
            user_id = verify_required_supabase_jwt(authorization)
            supabase_store.get_knowledge_base_for_user(str(payload.knowledge_base_id), user_id)
        except AuthError as exc:
            status = 503 if exc.code == "AUTH_NOT_CONFIGURED" else 401
            return _api_error(status, exc.code, exc.message)
        except SupabaseStoreError as exc:
            return _api_error(exc.status_code, exc.code, exc.message)

    return _word_stream(payload.title, payload.markdown)
