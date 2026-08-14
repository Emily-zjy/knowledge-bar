"""
Knowledge Bar Mind Map Agent (V2).

Orchestrates: Prompt → LLM Client → JSON Parse → Schema Repair → Pydantic → Trace.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from app.core.config import settings
from app.models.ai import GenerateMindMapRequest, GenerateMindMapResult, GenerationMetadata, MindMapData, MindMapNode
from app.prompts.mindmap_prompts import get_mindmap_prompt
from app.prompts.rollout import resolve_prompt_version
from app.services.llm_client import LLMError, LLMResponse, generate as llm_generate
from app.services.schema_repair import repair_mind_map

TRACE_DIR = Path(__file__).resolve().parent.parent.parent / "evaluation" / "runs"

logger = logging.getLogger(__name__)


class MindMapGenerationError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False, error_stage: str = "unknown") -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.error_stage = error_stage
        self.latency_ms: int | None = None
        self.retry_count: int | None = None
        self.input_length: int | None = None
        self.prompt_version: str | None = None
        self.repair_attempted = False
        self.repair_success = False


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


def _build_prompt(payload: GenerateMindMapRequest, version: str | None = None) -> list[dict[str, str]]:
    system = get_mindmap_prompt(version or settings.ai_prompt_version)
    max_depth = payload.requested_max_depth
    if max_depth <= 3:
        depth_instruction = (
            f"\n\nDepth constraint: produce a mind map with exactly {max_depth} levels "
            f"(root = level 1). Do not go deeper than level {max_depth}."
        )
    else:
        depth_instruction = (
            f"\n\nDepth requirement: the mind map MUST use {max_depth} levels "
            f"(root = level 1, deepest leaf = level {max_depth}). "
            f"The tree MUST have at least one path from root to a level-{max_depth} leaf. "
            f"Break down broad categories into sub-topics, then into specifics or examples. "
            f"For instance: Main Topic → Category → Sub-category → Detail/Example. "
            f"Use the natural hierarchy in the source: chapters→sections→points→details, "
            f"systems→components→sub-components→properties, "
            f"concepts→aspects→specifics→evidence. "
            f"Do NOT flatten the tree to 2-3 levels. "
            f"Do NOT exceed {max_depth} levels. "
            f"Every branch should aim for depth {max_depth} unless the content genuinely "
            f"has no further decomposition at that point."
        )
    system = system + depth_instruction
    user = (
        f"Knowledge base title: {payload.title}\n"
        f"Description: {payload.description or 'None'}\n"
        f"Notes:\n{payload.content_md}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _sanitize_json_string(text: str) -> str:
    """Fix common LLM JSON issues: trailing commas, control chars, single quotes."""
    result = text
    result = re.sub(r",\s*([}\]])", r"\1", result)
    result = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", result)
    return result


def _extract_json(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```\s*$", "", stripped).strip()

    def _try_parse(s: str) -> dict | None:
        try:
            obj = json.loads(s)
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None

    payload = _try_parse(stripped)
    if payload is not None:
        return payload

    sanitized = _sanitize_json_string(stripped)
    payload = _try_parse(sanitized)
    if payload is not None:
        return payload

    start = sanitized.find("{")
    end = sanitized.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MindMapGenerationError("AI_INVALID_JSON", "AI response did not contain parseable JSON.")

    payload = _try_parse(sanitized[start : end + 1])
    if payload is not None:
        return payload

    raise MindMapGenerationError("AI_INVALID_JSON", "AI response JSON is invalid.")


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


def _normalize_mind_map(raw: dict, fallback_title: str, max_depth: int = 6) -> MindMapData:
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

    _assert_depth(data, max_depth)
    return data


def _normalize_with_repair(raw: dict, fallback_title: str, max_depth: int = 6) -> tuple[MindMapData, bool, list[str]]:
    """Try normal validation first; on failure, attempt schema repair."""
    try:
        data = _normalize_mind_map(raw, fallback_title, max_depth)
        return data, False, []
    except MindMapGenerationError as first_error:
        initial_error = first_error

    repair_result = repair_mind_map(raw, max_depth=max_depth)
    if not repair_result.repaired:
        raise initial_error

    try:
        data = _normalize_mind_map(repair_result.data, fallback_title, max_depth)
        return data, True, repair_result.repairs
    except MindMapGenerationError as exc:
        raise MindMapGenerationError(
            "SCHEMA_REPAIR_FAILED",
            f"Schema repair attempted but validation still failed: {exc.message}",
        ) from exc


def _compute_tree_depth(nodes: list[MindMapNode]) -> int:
    children: dict[str | None, list[str]] = {}
    for n in nodes:
        children.setdefault(n.parentId, []).append(n.id)

    def _depth(node_id: str | None) -> int:
        kids = children.get(node_id, [])
        if not kids:
            return 0
        return 1 + max(_depth(k) for k in kids)

    return _depth(None)


def _save_trace(
    run_id: str,
    payload: GenerateMindMapRequest,
    result: GenerateMindMapResult | None,
    error: MindMapGenerationError | None,
    elapsed_ms: int,
    *,
    retry_count: int = 0,
    repair_attempted: bool = False,
    repair_success: bool = False,
    repair_actions: list[str] | None = None,
    token_usage: dict | None = None,
    llm_latency_ms: int = 0,
    rollout_meta: dict | None = None,
    prompt_version: str | None = None,
) -> None:
    try:
        TRACE_DIR.mkdir(parents=True, exist_ok=True)
        trace = {
            "run_id": run_id,
            "input_length": len(payload.content_md),
            "title": payload.title,
            "model": settings.ai_model,
            "provider": settings.ai_provider,
            "prompt_version": prompt_version or settings.ai_prompt_version,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "total_latency_ms": elapsed_ms,
            "llm_latency_ms": llm_latency_ms,
            "retry_count": retry_count,
            "repair_attempted": repair_attempted,
            "repair_success": repair_success,
            "repair_actions": repair_actions or [],
            "token_usage": token_usage or {},
            "success": result is not None,
            "error_type": error.code if error else None,
            "error": {"code": error.code, "message": error.message} if error else None,
            "output_json": {"title": result.mind_map.title, "node_count": len(result.mind_map.nodes)} if result else None,
        }
        if rollout_meta:
            trace["prompt_assignment_mode"] = rollout_meta.get("prompt_assignment_mode")
            trace["prompt_rollout_percentage"] = rollout_meta.get("prompt_rollout_percentage")
            trace["prompt_bucket"] = rollout_meta.get("prompt_bucket")
            trace["prompt_assignment_key_type"] = rollout_meta.get("prompt_assignment_key_type")
        trace_path = TRACE_DIR / f"{run_id}.json"
        trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        logger.debug("trace_save_failed", exc_info=True)


def generate_mind_map(
    payload: GenerateMindMapRequest,
    authorization: str | None,
    guest_session_id: str | None,
) -> GenerateMindMapResult:
    _ = authorization
    _ = guest_session_id

    run_id = str(uuid4())
    provider = settings.ai_provider.lower().strip()
    if provider == "mock":
        if settings.app_env == "production":
            raise MindMapGenerationError("MOCK_DISABLED", "Mock AI provider is disabled in production.")
        return _fallback_mind_map(payload)

    if settings.app_env == "production" and settings.ai_mock_fallback:
        raise MindMapGenerationError("MOCK_DISABLED", "AI_MOCK_FALLBACK must be false in production.")

    version, rollout_meta = resolve_prompt_version(
        user_id=None,
        knowledge_base_id=payload.knowledge_base_id,
    )
    messages = _build_prompt(payload, version)
    started = time.perf_counter()

    try:
        llm_response: LLMResponse = llm_generate(messages)
    except LLMError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        gen_error = MindMapGenerationError(
            exc.code,
            exc.message,
            retryable=exc.retryable,
            error_stage=exc.error_stage if exc.error_stage != "unknown" else "llm_call",
        )
        gen_error.latency_ms = elapsed_ms
        gen_error.retry_count = max(exc.attempts - 1, 0)
        gen_error.input_length = len(payload.content_md)
        gen_error.prompt_version = version
        _save_trace(
            run_id,
            payload,
            None,
            gen_error,
            elapsed_ms,
            retry_count=gen_error.retry_count,
            rollout_meta=rollout_meta,
            prompt_version=version,
        )

        if settings.ai_mock_fallback:
            logger.warning("ai_mock_fallback_used", extra={"error_code": exc.code})
            return _fallback_mind_map(payload)
        raise gen_error from exc

    llm_responses = [llm_response]
    raw: dict | None = None
    json_error: MindMapGenerationError | None = None
    for json_attempt in range(settings.ai_json_retries + 1):
        try:
            raw = _extract_json(llm_response.text)
            json_error = None
            break
        except MindMapGenerationError as exc:
            json_error = exc
            if json_attempt >= settings.ai_json_retries:
                break
            logger.warning(
                "ai_json_retry",
                extra={"attempt": json_attempt + 1, "error_stage": "json_parse"},
            )
            try:
                llm_response = llm_generate(messages, max_retries=0)
                llm_responses.append(llm_response)
            except LLMError as retry_exc:
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                gen_error = MindMapGenerationError(
                    retry_exc.code,
                    retry_exc.message,
                    retryable=retry_exc.retryable,
                    error_stage=retry_exc.error_stage if retry_exc.error_stage != "unknown" else "llm_call",
                )
                gen_error.latency_ms = elapsed_ms
                gen_error.retry_count = sum(response.attempts for response in llm_responses) + retry_exc.attempts - 1
                gen_error.input_length = len(payload.content_md)
                gen_error.prompt_version = version
                _save_trace(
                    run_id,
                    payload,
                    None,
                    gen_error,
                    elapsed_ms,
                    retry_count=gen_error.retry_count,
                    llm_latency_ms=sum(response.latency_ms for response in llm_responses),
                    rollout_meta=rollout_meta,
                    prompt_version=version,
                )
                raise gen_error from retry_exc

    llm_latency = sum(response.latency_ms for response in llm_responses)
    retry_count = sum(response.attempts for response in llm_responses) - 1
    if raw is None and json_error is not None:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        json_error.error_stage = "json_parse"
        json_error.latency_ms = elapsed_ms
        json_error.retry_count = retry_count
        json_error.input_length = len(payload.content_md)
        json_error.prompt_version = version
        _save_trace(run_id, payload, None, json_error, elapsed_ms, retry_count=retry_count, llm_latency_ms=llm_latency, token_usage=llm_response.usage, rollout_meta=rollout_meta, prompt_version=version)
        if settings.ai_mock_fallback:
            return _fallback_mind_map(payload)
        raise json_error

    try:
        mind_map, repaired, repair_actions = _normalize_with_repair(raw, payload.title, payload.requested_max_depth)
    except MindMapGenerationError as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        exc.error_stage = "schema_repair_failed" if exc.code == "SCHEMA_REPAIR_FAILED" else "schema_validation"
        exc.repair_attempted = exc.code == "SCHEMA_REPAIR_FAILED"
        exc.repair_success = False
        exc.latency_ms = elapsed_ms
        exc.retry_count = retry_count
        exc.input_length = len(payload.content_md)
        exc.prompt_version = version
        _save_trace(run_id, payload, None, exc, elapsed_ms, retry_count=retry_count, repair_attempted=exc.repair_attempted, repair_success=False, llm_latency_ms=llm_latency, token_usage=llm_response.usage, rollout_meta=rollout_meta, prompt_version=version)
        if settings.ai_mock_fallback:
            return _fallback_mind_map(payload)
        raise

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    logger.info("ai_generation_succeeded", extra={"elapsed_ms": elapsed_ms, "repaired": repaired, "retries": retry_count, "prompt_version": version})

    nodes = mind_map.nodes
    depth = _compute_tree_depth(nodes)
    token_usage = llm_response.usage or {}
    metadata = GenerationMetadata(
        input_length=len(payload.content_md),
        requested_depth=payload.requested_max_depth,
        input_tokens=token_usage.get("prompt_tokens"),
        output_tokens=token_usage.get("completion_tokens"),
        retry_count=retry_count,
        schema_repair_count=len(repair_actions) if repair_actions else 0,
        repair_attempted=repaired,
        repair_success=repaired,
        latency_ms=elapsed_ms,
        node_count=len(nodes),
        tree_depth=depth,
        prompt_version=version,
    )

    result = GenerateMindMapResult(generation_id=str(uuid4()), status="succeeded", mind_map=mind_map, metadata=metadata)
    _save_trace(
        run_id, payload, result, None, elapsed_ms,
        retry_count=retry_count,
        repair_attempted=repaired,
        repair_success=repaired,
        repair_actions=repair_actions,
        token_usage=llm_response.usage,
        llm_latency_ms=llm_latency,
        rollout_meta=rollout_meta,
        prompt_version=version,
    )
    return result
