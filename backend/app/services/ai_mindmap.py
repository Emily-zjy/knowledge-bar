from __future__ import annotations

import json
import logging
import re
import time
from uuid import uuid4

import httpx
from pydantic import ValidationError

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, GenerateMindMapResult, MindMapData, MindMapNode

logger = logging.getLogger(__name__)


class MindMapGenerationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def _extract_topics(content: str) -> list[str]:
    lines = [line.strip(" #*-0123456789.\t") for line in content.splitlines()]
    candidates = [line for line in lines if 3 <= len(line) <= 80]
    if not candidates:
        candidates = re.split(r"[.!?;\n]", content)

    topics: list[str] = []
    for item in candidates:
        text = item.strip()
        if text and text not in topics:
            topics.append(text)
        if len(topics) >= 8:
            break
    return topics or ["Core idea", "Key details", "Review path"]


def _fallback_mind_map(payload: GenerateMindMapRequest) -> GenerateMindMapResult:
    root_id = "node-root"
    nodes = [MindMapNode(id=root_id, parentId=None, text=payload.title, order=0)]
    for index, topic in enumerate(_extract_topics(payload.content_md), start=1):
        nodes.append(MindMapNode(id=f"node-{index}", parentId=root_id, text=topic[:80], order=index))

    return GenerateMindMapResult(
        generation_id=str(uuid4()),
        status="succeeded",
        mind_map=MindMapData(title=payload.title, nodes=nodes),
    )


def _build_prompt(payload: GenerateMindMapRequest) -> list[dict[str, str]]:
    system = (
        "You are Knowledge Bar's knowledge-structure assistant. Convert the user's notes into a mind map JSON object. "
        "Return only JSON, with no markdown fence and no extra prose. The schema is: "
        '{"title":"string","nodes":[{"id":"node-root","parentId":null,"text":"central topic","order":0}]}. '
        "Rules: exactly one root node with parentId null; every non-root parentId must point to an existing node; "
        "node text must be concise; use at most 25 nodes; preserve the source meaning without inventing facts."
    )
    user = (
        f"Knowledge base title: {payload.title}\n"
        f"Description: {payload.description or 'None'}\n"
        f"Notes:\n{payload.content_md}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _chat_completions_url() -> str:
    base_url = (settings.resolved_ai_base_url or "").strip().rstrip("/")
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
        stripped = re.sub(r"```\s*$", "", stripped).strip()

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise MindMapGenerationError("AI_INVALID_JSON", "AI response did not contain parseable JSON.")
        try:
            payload = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise MindMapGenerationError("AI_INVALID_JSON", "AI response JSON is invalid.") from exc

    if not isinstance(payload, dict):
        raise MindMapGenerationError("AI_INVALID_JSON", "AI response JSON must be an object.")
    return payload


def _assert_depth(data: MindMapData, max_depth: int = 6) -> None:
    children: dict[str | None, list[str]] = {}
    for node in data.nodes:
        children.setdefault(node.parentId, []).append(node.id)

    def walk(node_id: str, depth: int, visiting: set[str]) -> None:
        if depth > max_depth:
            raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map exceeds the maximum depth.")
        if node_id in visiting:
            raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map contains a cycle.")
        for child_id in children.get(node_id, []):
            walk(child_id, depth + 1, visiting | {node_id})

    root = next(node for node in data.nodes if node.parentId is None)
    walk(root.id, 1, set())


def _normalize_mind_map(raw: dict, fallback_title: str) -> MindMapData:
    try:
        data = MindMapData.model_validate({"title": raw.get("title") or fallback_title, "nodes": raw.get("nodes") or []})
    except ValidationError as exc:
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI response failed mind map schema validation.") from exc

    if len(data.nodes) > 25:
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map has too many nodes.")

    ids = [node.id for node in data.nodes]
    if len(ids) != len(set(ids)):
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map contains duplicate node IDs.")

    root_nodes = [node for node in data.nodes if node.parentId is None]
    if len(root_nodes) != 1:
        raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map must contain exactly one root node.")

    known_ids = set(ids)
    for node in data.nodes:
        if node.parentId is not None and node.parentId not in known_ids:
            raise MindMapGenerationError("AI_INVALID_SCHEMA", "AI mind map contains an invalid parentId.")

    _assert_depth(data)
    return data


def _request_openai_compatible(payload: GenerateMindMapRequest) -> MindMapData:
    if not settings.ai_api_key:
        raise MindMapGenerationError("AI_KEY_MISSING", "AI_API_KEY is not configured.")

    try:
        with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
            response = client.post(
                _chat_completions_url(),
                headers={"Authorization": f"Bearer {settings.ai_api_key}", "Content-Type": "application/json"},
                json={
                    "model": settings.ai_model,
                    "messages": _build_prompt(payload),
                    "temperature": 0.2,
                    "response_format": {"type": "json_object"},
                },
            )
    except httpx.TimeoutException as exc:
        raise MindMapGenerationError("AI_TIMEOUT", "AI request timed out.", retryable=True) from exc
    except httpx.TransportError as exc:
        raise MindMapGenerationError("AI_NETWORK_ERROR", "AI network request failed.", retryable=True) from exc

    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise MindMapGenerationError("AI_TEMPORARY_ERROR", f"AI temporary HTTP error {response.status_code}.", retryable=True)
    if response.status_code >= 400:
        raise MindMapGenerationError("AI_HTTP_ERROR", f"AI request failed with HTTP {response.status_code}.")

    body = response.json()
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise MindMapGenerationError("AI_EMPTY_RESPONSE", "AI response content is empty.")
    return _normalize_mind_map(_extract_json(content), payload.title)


def _request_anthropic(payload: GenerateMindMapRequest) -> MindMapData:
    if not settings.ai_api_key:
        raise MindMapGenerationError("AI_KEY_MISSING", "AI_API_KEY is not configured.")

    messages = _build_prompt(payload)
    try:
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
                    "system": messages[0]["content"],
                    "messages": [{"role": "user", "content": messages[1]["content"]}],
                },
            )
    except httpx.TimeoutException as exc:
        raise MindMapGenerationError("AI_TIMEOUT", "AI request timed out.", retryable=True) from exc
    except httpx.TransportError as exc:
        raise MindMapGenerationError("AI_NETWORK_ERROR", "AI network request failed.", retryable=True) from exc

    if response.status_code in {408, 409, 425, 429} or response.status_code >= 500:
        raise MindMapGenerationError("AI_TEMPORARY_ERROR", f"AI temporary HTTP error {response.status_code}.", retryable=True)
    if response.status_code >= 400:
        raise MindMapGenerationError("AI_HTTP_ERROR", f"AI request failed with HTTP {response.status_code}.")

    body = response.json()
    content_blocks = body.get("content", [])
    content = "".join(block.get("text", "") for block in content_blocks if block.get("type") == "text")
    if not content:
        raise MindMapGenerationError("AI_EMPTY_RESPONSE", "AI response content is empty.")
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

    attempts = max(settings.ai_max_retries, 0) + 1
    last_error: MindMapGenerationError | None = None
    started = time.perf_counter()
    for attempt in range(1, attempts + 1):
        try:
            if provider == "anthropic":
                mind_map = _request_anthropic(payload)
            else:
                mind_map = _request_openai_compatible(payload)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info("ai_generation_succeeded", extra={"attempt": attempt, "elapsed_ms": elapsed_ms})
            return GenerateMindMapResult(generation_id=str(uuid4()), status="succeeded", mind_map=mind_map)
        except MindMapGenerationError as exc:
            last_error = exc
            if not exc.retryable or attempt >= attempts:
                break
            logger.warning("ai_generation_retry", extra={"attempt": attempt, "error_code": exc.code})

    if settings.ai_mock_fallback:
        logger.warning("ai_mock_fallback_used", extra={"error_code": last_error.code if last_error else "UNKNOWN"})
        return _fallback_mind_map(payload)

    if last_error:
        raise last_error
    raise MindMapGenerationError("AI_UNKNOWN_ERROR", "AI generation failed.")
