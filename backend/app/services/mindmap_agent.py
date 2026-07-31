"""Mind map agent orchestration using AISuite.

Handles the end-to-end pipeline:
1. Prepare text
2. Chunk if needed
3. Call LLM to generate structured mind map
4. Save draft
5. Validate
6. Auto-fix on validation failure (max 2 retries)
7. Render for frontend
"""

from __future__ import annotations

import json
import logging
import re
from uuid import uuid4

import httpx

from app.core.config import settings
from app.models.mindmap import (
    GenerateRequest,
    MindMapState,
    ValidationResult,
)
from app.services.actions import (
    chunk_text,
    prepare_text,
    render_mindmap,
    save_mindmap_draft,
    validate_mindmap,
)

logger = logging.getLogger(__name__)

MAX_RETRY = 2

SYSTEM_PROMPT = """你是长文本思维导图生成Agent。

你的任务不是简单总结，而是将用户原文整理成层级清楚、节点简洁、可以追溯来源的思维导图。

必须遵守：
1. 严格依据原文，不得编造原文没有的信息；
2. 中心主题必须准确概括原文；
3. 相近内容应合并；
4. 不同类别不得错误混合；
5. 每个节点使用简短名词或短语（不超过20字）；
6. 节点不得写成长段落；
7. 最大层级为{max_depth}层（包括根节点）；
8. 一级分支建议为3至7个；
9. 每个节点必须填写有效source_ids（引用来源段落ID列表）；
10. 流程型内容应体现先后顺序；
11. 知识型内容应按照概念关系分类；
12. 校验失败时只修改错误节点，不得无故推翻正确结构；
13. 不允许调用未注册工具；
14. 不允许生成或执行任意Python代码；
15. 最终必须提交符合结构化格式的JSON结果。

你必须输出一个JSON对象，格式为：
{{
  "title": "中心主题文字",
  "map_type": "{map_type}",
  "nodes": [
    {{
      "id": "node-root",
      "parent_id": null,
      "text": "中心主题",
      "level": 0,
      "order": 0,
      "side": null,
      "source_ids": []
    }},
    {{
      "id": "node-1",
      "parent_id": "node-root",
      "text": "一级分支名称",
      "level": 1,
      "order": 1,
      "side": "right",
      "source_ids": ["p-abc12345"]
    }}
  ]
}}

规则：
- 有且只有一个根节点（parent_id为null，level为0）
- 一级分支 side 交替为 "right" 和 "left"
- 每个非根节点必须有至少一个有效的 source_ids
- id 使用 "node-root", "node-1", "node-2" ... 格式
- level 从0开始，root=0, 一级=1, 二级=2...
- 只输出JSON，不要输出解释或Markdown代码块
"""

FIX_PROMPT = """上一次生成的思维导图校验失败。请根据以下错误信息修正：

错误列表：
{errors}

警告列表：
{warnings}

当前的草稿节点：
{current_nodes}

请只修改有问题的节点，不要推翻正确结构。输出修正后的完整JSON（与之前相同格式）。
只输出JSON，不要输出解释。
"""


def _call_llm(messages: list[dict], temperature: float = 0.2) -> str:
    """Call LLM using the configured provider via OpenAI-compatible API."""
    if not settings.ai_api_key:
        raise RuntimeError("AI_API_KEY not configured")

    base_url = (settings.ai_api_base_url or "").strip().rstrip("/")
    if not base_url:
        url = "https://api.openai.com/v1/chat/completions"
    elif base_url.endswith("/chat/completions"):
        url = base_url
    elif base_url.endswith("/v1"):
        url = f"{base_url}/chat/completions"
    else:
        url = f"{base_url}/v1/chat/completions"

    with httpx.Client(timeout=settings.ai_timeout_seconds) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.ai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.ai_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4000,
            },
        )

    if response.status_code >= 400:
        logger.error(f"LLM HTTP error: {response.status_code} - {response.text[:200]}")
        raise RuntimeError(f"AI接口请求失败：HTTP {response.status_code}")

    body = response.json()
    content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not content:
        raise RuntimeError("AI返回内容为空")
    return content


def _extract_json_from_response(text: str) -> dict:
    """Extract JSON from LLM response, handling markdown code blocks."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```\s*$", "", stripped).strip()

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("AI没有返回可解析的JSON")
        return json.loads(stripped[start:end + 1])


def _generate_with_llm(
    paragraphs: list[dict],
    title: str | None,
    max_depth: int,
    map_type: str,
) -> dict:
    """Generate mind map structure via LLM."""
    para_text = "\n\n".join(
        f"[段落ID: {p['id']}]\n{p['text']}" for p in paragraphs
    )

    system_msg = SYSTEM_PROMPT.format(max_depth=max_depth, map_type=map_type)
    user_msg = f"请将以下文本整理为思维导图：\n\n{para_text}"
    if title:
        user_msg = f"用户指定的标题：{title}\n\n{user_msg}"

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    response_text = _call_llm(messages)
    return _extract_json_from_response(response_text)


def _fix_with_llm(
    errors: list[dict],
    warnings: list[dict],
    current_nodes: list[dict],
    paragraphs: list[dict],
    max_depth: int,
    map_type: str,
) -> dict:
    """Ask LLM to fix validation errors."""
    system_msg = SYSTEM_PROMPT.format(max_depth=max_depth, map_type=map_type)
    user_msg = FIX_PROMPT.format(
        errors=json.dumps(errors, ensure_ascii=False, indent=2),
        warnings=json.dumps(warnings[:5], ensure_ascii=False, indent=2),
        current_nodes=json.dumps(current_nodes, ensure_ascii=False, indent=2),
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    response_text = _call_llm(messages)
    return _extract_json_from_response(response_text)


def _local_fallback(paragraphs: list[dict], title: str) -> dict | None:
    """Deterministic fallback is DISABLED for production use.

    When LLM fails, return None to signal failure rather than
    generating fake placeholder content.
    """
    return None


def generate_mindmap_pipeline(request: GenerateRequest) -> MindMapState:
    """Execute the full mind map generation pipeline.

    Returns a complete MindMapState with render data ready for frontend.
    """
    task_id = str(uuid4())
    state = MindMapState(task_id=task_id, status="processing", raw_text=request.text)

    # Step 1: Prepare text
    prepared = prepare_text(request.text)
    state.paragraphs = [
        __import__("app.models.mindmap", fromlist=["SourceParagraph"]).SourceParagraph(**p)
        for p in prepared["paragraphs"]
    ]
    paragraphs_data = prepared["paragraphs"]

    # Step 2: Chunk if needed
    if prepared["needs_chunking"]:
        chunks = chunk_text(paragraphs_data)
        all_para_ids = []
        for chunk in chunks:
            all_para_ids.extend(chunk["paragraph_ids"])
    else:
        chunks = None

    # Determine title
    title = request.title or ""
    if not title and paragraphs_data:
        first_text = paragraphs_data[0]["text"]
        first_line = first_text.split("\n")[0].strip(" #*-")
        if 2 <= len(first_line) <= 60:
            title = first_line

    state.title = title or "未命名导图"

    # Step 3: Generate with LLM (or fail)
    try:
        raw_result = _generate_with_llm(
            paragraphs=paragraphs_data,
            title=title,
            max_depth=request.max_depth,
            map_type=request.map_type,
        )
    except Exception as e:
        logger.warning(f"LLM generation failed: {e}")
        state.status = "failed"
        state.error_message = f"AI生成失败：{e}"
        return state

    # Step 4: Save draft
    draft_result = save_mindmap_draft(
        task_id=task_id,
        title=raw_result.get("title", state.title),
        map_type=raw_result.get("map_type", request.map_type),
        nodes=raw_result.get("nodes", []),
    )
    state.title = raw_result.get("title", state.title)

    # Step 5: Validate
    state.status = "validating"
    draft_data = draft_result["draft"]
    validation = validate_mindmap(draft_data, paragraphs_data, request.max_depth)

    # Step 6: Auto-fix loop (max 2 retries)
    retry_count = 0
    while not validation["passed"] and retry_count < MAX_RETRY:
        retry_count += 1
        logger.info(f"Validation failed (attempt {retry_count}), requesting LLM fix...")
        try:
            fixed_result = _fix_with_llm(
                errors=validation["errors"],
                warnings=validation["warnings"],
                current_nodes=draft_data["nodes"],
                paragraphs=paragraphs_data,
                max_depth=request.max_depth,
                map_type=request.map_type,
            )
            draft_result = save_mindmap_draft(
                task_id=task_id,
                title=fixed_result.get("title", state.title),
                map_type=fixed_result.get("map_type", request.map_type),
                nodes=fixed_result.get("nodes", []),
            )
            draft_data = draft_result["draft"]
            validation = validate_mindmap(draft_data, paragraphs_data, request.max_depth)
            validation["retry_count"] = retry_count
        except Exception as e:
            logger.warning(f"LLM fix attempt {retry_count} failed: {e}")
            break

    state.validation = ValidationResult(**validation)
    state.draft = __import__("app.models.mindmap", fromlist=["MindMapDraft"]).MindMapDraft(**draft_data)

    if not validation["passed"]:
        state.status = "failed"
        error_msgs = [e["message"] for e in validation["errors"][:3]]
        state.error_message = f"思维导图校验失败：{'；'.join(error_msgs)}"
        return state

    # Step 7: Render
    render_data = render_mindmap(draft_data)
    state.render_data = __import__("app.models.mindmap", fromlist=["RenderData"]).RenderData(**render_data)
    state.status = "succeeded"

    return state
