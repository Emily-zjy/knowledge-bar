import json
import re
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, GenerateMindMapResult, MindMapData, MindMapNode


class MindMapGenerationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _extract_topics(content: str) -> list[str]:
    lines = [line.strip(" #*-0123456789.\t") for line in content.splitlines()]
    candidates = [line for line in lines if 3 <= len(line) <= 80]
    if not candidates:
        candidates = re.split(r"[。！？\n]", content)

    topics: list[str] = []
    for item in candidates:
        text = item.strip()
        if text and text not in topics:
            topics.append(text)
        if len(topics) >= 8:
            break
    return topics or ["核心概念", "重点内容", "复习线索"]


def _fallback_mind_map(payload: GenerateMindMapRequest) -> GenerateMindMapResult:
    root_id = "node-root"
    nodes = [
        MindMapNode(id=root_id, parentId=None, text=payload.title, order=0),
    ]
    for index, topic in enumerate(_extract_topics(payload.content_md), start=1):
        nodes.append(
            MindMapNode(
                id=f"node-{index}",
                parentId=root_id,
                text=topic[:80],
                order=index,
            ),
        )

    return GenerateMindMapResult(
        generation_id=str(uuid4()),
        status="succeeded",
        mind_map=MindMapData(title=payload.title, nodes=nodes),
    )


def _build_prompt(payload: GenerateMindMapRequest) -> list[dict[str, str]]:
    system = (
        "你是 Knowledge Bar 的学习资料结构化助手。"
        "请把用户输入的自由笔记整理为横向思维导图 JSON。"
        "只输出 JSON，不要输出解释、Markdown 代码块或额外文本。"
        "JSON 必须符合："
        '{"title":"string","nodes":[{"id":"node-root","parentId":null,"text":"中心主题","order":0}]}。'
        "节点 text 要简洁，适合显示在思维导图节点内；最多 25 个节点；必须有且只有一个 parentId 为 null 的根节点。"
    )
    user = (
        f"知识库名称：{payload.title}\n"
        f"知识库描述：{payload.description or '无'}\n"
        f"用户笔记：\n{payload.content_md}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _chat_completions_url() -> str:
    base_url = (settings.ai_api_base_url or "").strip().rstrip("/")
    if not base_url:
        return "https://api.openai.com/v1/chat/completions"
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise MindMapGenerationError("AI_INVALID_JSON", "AI 没有返回可解析的 JSON。")
        return json.loads(stripped[start : end + 1])


def _normalize_mind_map(raw: dict, fallback_title: str) -> MindMapData:
    data = MindMapData.model_validate(
        {
            "title": raw.get("title") or fallback_title,
            "nodes": raw.get("nodes") or [],
        },
    )
    root_nodes = [node for node in data.nodes if node.parentId is None]
    if len(root_nodes) != 1:
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI 返回的思维导图必须包含一个中心节点。")

    known_ids = {node.id for node in data.nodes}
    for node in data.nodes:
        if node.parentId is not None and node.parentId not in known_ids:
            raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI 返回的思维导图存在无效父节点。")

    return data


def _generate_with_openai_compatible(payload: GenerateMindMapRequest) -> MindMapData:
    if not settings.ai_api_key:
        raise MindMapGenerationError("AI_KEY_MISSING", "后端缺少 AI_API_KEY。")

    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        response = client.post(
            _chat_completions_url(),
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": _build_prompt(payload),
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
            },
        )

    if response.status_code >= 400:
        raise MindMapGenerationError("AI_HTTP_ERROR", f"AI 接口请求失败：HTTP {response.status_code}")

    body = response.json()
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise MindMapGenerationError("AI_EMPTY_RESPONSE", "AI 返回内容为空。")
    return _normalize_mind_map(_extract_json(content), payload.title)


def _generate_with_anthropic(payload: GenerateMindMapRequest) -> MindMapData:
    if not settings.ai_api_key:
        raise MindMapGenerationError("AI_KEY_MISSING", "后端缺少 AI_API_KEY。")

    messages = _build_prompt(payload)
    system = messages[0]["content"]
    user = messages[1]["content"]
    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        response = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": settings.ai_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "max_tokens": 1800,
                "temperature": 0.2,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )

    if response.status_code >= 400:
        raise MindMapGenerationError("AI_HTTP_ERROR", f"AI 接口请求失败：HTTP {response.status_code}")

    body = response.json()
    content_blocks = body.get("content", [])
    content = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
    if not content:
        raise MindMapGenerationError("AI_EMPTY_RESPONSE", "AI 返回内容为空。")
    return _normalize_mind_map(_extract_json(content), payload.title)


def generate_mind_map(
    payload: GenerateMindMapRequest,
    authorization: str | None,
    guest_session_id: str | None,
) -> GenerateMindMapResult:
    _ = authorization
    _ = guest_session_id

    provider = settings.ai_provider.lower().strip()
    if provider == "mock":
        return _fallback_mind_map(payload)

    try:
        if provider == "anthropic":
            mind_map = _generate_with_anthropic(payload)
        else:
            mind_map = _generate_with_openai_compatible(payload)
    except Exception as exc:
        if settings.ai_mock_fallback:
            return _fallback_mind_map(payload)
        if isinstance(exc, MindMapGenerationError):
            raise
        raise MindMapGenerationError("AI_UNKNOWN_ERROR", "AI 生成失败，请稍后重试。") from exc

    return GenerateMindMapResult(
        generation_id=str(uuid4()),
        status="succeeded",
        mind_map=mind_map,
    )
