from io import BytesIO
from urllib.parse import quote

from docx import Document
from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from app.models.ai import (
    ApiError,
    ApiResponse,
    ExportWordRequest,
    GenerateMindMapRequest,
    GenerateMindMapResult,
)
from app.services.ai_mindmap import MindMapGenerationError, generate_mind_map
from app.services.auth import AuthError, verify_optional_supabase_jwt

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/mindmap/generate", response_model=ApiResponse[GenerateMindMapResult])
def generate_mindmap(
    payload: GenerateMindMapRequest,
    authorization: str | None = Header(default=None),
    x_guest_session_id: str | None = Header(default=None),
) -> ApiResponse[GenerateMindMapResult]:
    try:
        verify_optional_supabase_jwt(authorization)
        result = generate_mind_map(
            payload=payload,
            authorization=authorization,
            guest_session_id=x_guest_session_id,
        )
        return ApiResponse(success=True, data=result)
    except (AuthError, MindMapGenerationError) as exc:
        return ApiResponse(success=False, error=ApiError(code=exc.code, message=exc.message))


@router.post("/export/word")
def export_word(payload: ExportWordRequest) -> StreamingResponse:
    document = Document()
    document.add_heading(payload.title, level=1)

    if payload.markdown.strip():
        for raw_line in payload.markdown.splitlines():
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
                document.add_paragraph(line)
    else:
        document.add_paragraph("暂无内容")

    buffer = BytesIO()
    document.save(buffer)
    buffer.seek(0)
    filename = quote(f"{payload.title}.docx")
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
