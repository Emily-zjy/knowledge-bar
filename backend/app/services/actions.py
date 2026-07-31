"""Python Actions for the mind map agent pipeline.

These are the ONLY functions the LLM agent is allowed to invoke.
Each action is a pure, deterministic Python function with type annotations.
"""

from __future__ import annotations

import hashlib
import re
from uuid import uuid4

from app.models.mindmap import (
    MindMapDraft,
    MindMapNode,
    RenderData,
    RenderEdge,
    RenderNode,
    SourceParagraph,
    ValidationError,
    ValidationResult,
    ValidationWarning,
)


# ---------------------------------------------------------------------------
# Action 1: prepare_text
# ---------------------------------------------------------------------------

def prepare_text(raw_text: str) -> dict:
    """Clean raw input text and split into paragraphs.

    Args:
        raw_text: The user's raw input text.

    Returns:
        Dictionary with clean_text, paragraphs, char_count, needs_chunking.
    """
    text = raw_text.strip()
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"[^\S\n]+$", "", text, flags=re.MULTILINE)

    blocks = re.split(r"\n{2,}", text)
    paragraphs: list[SourceParagraph] = []
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        para_id = f"p-{hashlib.md5(f'{i}:{block[:50]}'.encode()).hexdigest()[:8]}"
        paragraphs.append(SourceParagraph(id=para_id, text=block, order=i))

    char_count = len(text)
    needs_chunking = char_count > 8000

    return {
        "clean_text": text,
        "paragraphs": [p.model_dump() for p in paragraphs],
        "char_count": char_count,
        "needs_chunking": needs_chunking,
    }


# ---------------------------------------------------------------------------
# Action 2: chunk_text
# ---------------------------------------------------------------------------

def chunk_text(paragraphs: list[dict], max_chunk_chars: int = 6000) -> list[dict]:
    """Split paragraphs into chunks for processing.

    Only invoked when text exceeds model context safety threshold.
    Splits at heading/paragraph boundaries, never mid-sentence.

    Args:
        paragraphs: List of paragraph dicts with id, text, order.
        max_chunk_chars: Maximum characters per chunk.

    Returns:
        List of chunk dicts, each containing paragraph_ids and text.
    """
    chunks: list[dict] = []
    current_chunk_text = ""
    current_chunk_ids: list[str] = []

    for para in paragraphs:
        para_text = para["text"]
        if current_chunk_text and (len(current_chunk_text) + len(para_text) + 2) > max_chunk_chars:
            chunks.append({
                "chunk_index": len(chunks),
                "paragraph_ids": current_chunk_ids[:],
                "text": current_chunk_text.strip(),
            })
            current_chunk_text = ""
            current_chunk_ids = []

        current_chunk_text += para_text + "\n\n"
        current_chunk_ids.append(para["id"])

    if current_chunk_text.strip():
        chunks.append({
            "chunk_index": len(chunks),
            "paragraph_ids": current_chunk_ids[:],
            "text": current_chunk_text.strip(),
        })

    return chunks


# ---------------------------------------------------------------------------
# Action 3: save_mindmap_draft
# ---------------------------------------------------------------------------

def save_mindmap_draft(task_id: str, title: str, map_type: str, nodes: list[dict]) -> dict:
    """Validate and save a mind map draft from LLM output.

    Args:
        task_id: The generation task ID.
        title: Mind map title.
        map_type: Type of mind map (auto/knowledge/process).
        nodes: List of node dicts from LLM.

    Returns:
        Dictionary with task_id, draft_version, node_count, status.
    """
    validated_nodes = []
    for node_data in nodes:
        validated_nodes.append(MindMapNode.model_validate(node_data))

    draft = MindMapDraft(title=title, map_type=map_type, nodes=validated_nodes)

    return {
        "task_id": task_id,
        "draft_version": 1,
        "node_count": len(draft.nodes),
        "status": "draft_saved",
        "draft": draft.model_dump(),
    }


# ---------------------------------------------------------------------------
# Action 4: validate_mindmap
# ---------------------------------------------------------------------------

def validate_mindmap(draft: dict, paragraphs: list[dict], max_depth: int = 4) -> dict:
    """Comprehensive validation of a mind map draft.

    Checks:
    - Central topic exists
    - No duplicate node IDs
    - All parent_ids are valid
    - No orphan nodes
    - No cycles
    - Max depth not exceeded
    - No single parent with too many children (>10)
    - Node text not too long
    - No duplicate nodes
    - First-level branches not empty
    - source_ids are valid
    - Content traceable to source

    Args:
        draft: The MindMapDraft as a dict.
        paragraphs: Source paragraphs for traceability check.
        max_depth: Maximum allowed tree depth.

    Returns:
        ValidationResult as dict.
    """
    errors: list[ValidationError] = []
    warnings: list[ValidationWarning] = []
    nodes = draft.get("nodes", [])
    paragraph_ids = {p["id"] for p in paragraphs}

    # Check: central topic exists
    root_nodes = [n for n in nodes if n.get("parent_id") is None]
    if len(root_nodes) == 0:
        errors.append(ValidationError(code="NO_ROOT", message="缺少中心主题节点"))
    elif len(root_nodes) > 1:
        errors.append(ValidationError(code="MULTIPLE_ROOTS", message=f"存在 {len(root_nodes)} 个根节点，应只有1个"))

    # Check: duplicate node IDs
    node_ids = [n["id"] for n in nodes]
    seen_ids = set()
    for nid in node_ids:
        if nid in seen_ids:
            errors.append(ValidationError(code="DUPLICATE_ID", message=f"重复节点ID: {nid}", node_id=nid))
        seen_ids.add(nid)

    id_set = set(node_ids)

    # Check: parent_id validity
    for n in nodes:
        pid = n.get("parent_id")
        if pid is not None and pid not in id_set:
            errors.append(ValidationError(
                code="INVALID_PARENT", message=f"节点 {n['id']} 的 parent_id '{pid}' 不存在", node_id=n["id"]
            ))

    # Check: cycles
    def has_cycle(node_id: str, visited: set) -> bool:
        if node_id in visited:
            return True
        visited.add(node_id)
        children = [n for n in nodes if n.get("parent_id") == node_id]
        for child in children:
            if has_cycle(child["id"], visited.copy()):
                return True
        return False

    if root_nodes:
        parent_map = {n["id"]: n.get("parent_id") for n in nodes}
        for n in nodes:
            chain = set()
            current = n["id"]
            while current is not None:
                if current in chain:
                    errors.append(ValidationError(code="CYCLE", message=f"节点 {n['id']} 存在循环引用", node_id=n["id"]))
                    break
                chain.add(current)
                current = parent_map.get(current)

    # Check: orphan nodes (not reachable from root)
    if root_nodes and not errors:
        reachable = set()

        def walk(nid: str):
            reachable.add(nid)
            for child in nodes:
                if child.get("parent_id") == nid and child["id"] not in reachable:
                    walk(child["id"])

        walk(root_nodes[0]["id"])
        for n in nodes:
            if n["id"] not in reachable:
                errors.append(ValidationError(code="ORPHAN", message=f"孤立节点: {n['id']}", node_id=n["id"]))

    # Check: max depth
    def get_depth(node_id: str) -> int:
        children = [n for n in nodes if n.get("parent_id") == node_id]
        if not children:
            return 0
        return 1 + max(get_depth(c["id"]) for c in children)

    if root_nodes:
        actual_depth = get_depth(root_nodes[0]["id"])
        if actual_depth > max_depth:
            errors.append(ValidationError(
                code="EXCEEDS_DEPTH", message=f"层级深度 {actual_depth} 超过限制 {max_depth}"
            ))

    # Check: too many children per parent
    children_count: dict[str, int] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid:
            children_count[pid] = children_count.get(pid, 0) + 1
    for pid, count in children_count.items():
        if count > 10:
            warnings.append(ValidationWarning(
                code="TOO_MANY_CHILDREN", message=f"节点 {pid} 有 {count} 个子节点，建议不超过10个", node_id=pid
            ))

    # Check: node text too long
    for n in nodes:
        if len(n.get("text", "")) > 80:
            warnings.append(ValidationWarning(
                code="TEXT_TOO_LONG", message=f"节点 {n['id']} 文字过长({len(n['text'])}字)", node_id=n["id"]
            ))

    # Check: duplicate node text
    texts_seen: dict[str, str] = {}
    for n in nodes:
        text_lower = n.get("text", "").strip().lower()
        if text_lower in texts_seen:
            warnings.append(ValidationWarning(
                code="DUPLICATE_TEXT",
                message=f"节点 {n['id']} 与 {texts_seen[text_lower]} 内容重复",
                node_id=n["id"],
            ))
        else:
            texts_seen[text_lower] = n["id"]

    # Check: first-level branches not empty
    if root_nodes:
        first_level = [n for n in nodes if n.get("parent_id") == root_nodes[0]["id"]]
        if len(first_level) == 0:
            errors.append(ValidationError(code="NO_BRANCHES", message="一级分支为空"))
        elif len(first_level) < 2:
            warnings.append(ValidationWarning(code="FEW_BRANCHES", message="一级分支数量过少，建议3-7个"))

    # Check: source_ids validity
    for n in nodes:
        if n.get("parent_id") is None:
            continue
        source_ids = n.get("source_ids", [])
        if not source_ids:
            warnings.append(ValidationWarning(
                code="MISSING_SOURCE", message=f"节点 {n['id']} 缺少来源引用", node_id=n["id"]
            ))
        else:
            for sid in source_ids:
                if sid not in paragraph_ids:
                    warnings.append(ValidationWarning(
                        code="INVALID_SOURCE", message=f"节点 {n['id']} 引用了无效段落 {sid}", node_id=n["id"]
                    ))

    # Check: reject generic/placeholder titles
    GENERIC_TITLES = {"知识导图", "思维导图", "导图", "mind map", "mindmap", "untitled"}
    if root_nodes:
        root_text = root_nodes[0].get("text", "").strip().lower()
        if root_text in GENERIC_TITLES or not root_text:
            errors.append(ValidationError(
                code="GENERIC_TITLE", message="中心主题过于通用或为空，应概括原文核心内容", node_id=root_nodes[0]["id"]
            ))

    # Check: reject placeholder node texts
    PLACEHOLDER_TEXTS = {"重点内容", "核心概念", "复习线索", "其他内容", "主题", "内容", "概述", "总结"}
    for n in nodes:
        if n.get("text", "").strip() in PLACEHOLDER_TEXTS:
            errors.append(ValidationError(
                code="PLACEHOLDER_NODE", message=f"节点 {n['id']} 使用了占位文字「{n['text']}」，需要具体内容", node_id=n["id"]
            ))

    # Check: long text should produce sufficient branches
    total_source_chars = sum(len(p.get("text", "")) for p in paragraphs)
    if root_nodes:
        first_level = [n for n in nodes if n.get("parent_id") == root_nodes[0]["id"]]
        if total_source_chars > 200 and len(first_level) < 4:
            errors.append(ValidationError(
                code="TOO_FEW_BRANCHES",
                message=f"原文较长({total_source_chars}字)但仅生成{len(first_level)}个一级分支，至少需要4个"
            ))

    # Check: long text should produce second-level nodes
    second_level = [n for n in nodes if n.get("level", 0) == 2]
    if total_source_chars > 200 and len(second_level) == 0:
        errors.append(ValidationError(
            code="NO_SECOND_LEVEL",
            message="原文较长但未生成二级节点，结构过于扁平"
        ))

    # Check: sufficient total nodes for long text
    if total_source_chars > 300 and len(nodes) < 10:
        errors.append(ValidationError(
            code="TOO_FEW_NODES",
            message=f"原文{total_source_chars}字但仅生成{len(nodes)}个节点，至少需要10个"
        ))

    # Calculate score
    score = 100
    score -= len(errors) * 20
    score -= len(warnings) * 5
    score = max(0, min(100, score))

    passed = len(errors) == 0

    result = ValidationResult(
        passed=passed,
        score=score,
        errors=errors,
        warnings=warnings,
        retry_count=0,
    )
    return result.model_dump()


# ---------------------------------------------------------------------------
# Action 5: render_mindmap
# ---------------------------------------------------------------------------

def render_mindmap(draft: dict) -> dict:
    """Convert a validated mind map draft to frontend-renderable nodes and edges.

    Computes a hierarchical layout with left/right balancing.
    Does NOT call LLM. Pure Python layout computation.

    Args:
        draft: The MindMapDraft as a dict.

    Returns:
        RenderData as dict with nodes (positioned) and edges.
    """
    nodes = draft.get("nodes", [])
    title = draft.get("title", "")

    root_nodes = [n for n in nodes if n.get("parent_id") is None]
    if not root_nodes:
        return RenderData(nodes=[], edges=[]).model_dump()

    root = root_nodes[0]

    # Build children map
    children_map: dict[str, list[dict]] = {}
    for n in nodes:
        pid = n.get("parent_id")
        if pid:
            children_map.setdefault(pid, []).append(n)

    # Sort children by order
    for children in children_map.values():
        children.sort(key=lambda c: c.get("order", 0))

    # Assign sides to first-level nodes (alternate left/right)
    first_level = children_map.get(root["id"], [])
    for i, child in enumerate(first_level):
        if child.get("side") is None:
            child["side"] = "right" if i % 2 == 0 else "left"

    # Layout constants
    NODE_WIDTH = 180
    NODE_HEIGHT = 60
    H_GAP = 80
    V_GAP = 30

    render_nodes: list[RenderNode] = []
    render_edges: list[RenderEdge] = []

    def compute_subtree_height(node_id: str) -> float:
        children = children_map.get(node_id, [])
        if not children:
            return NODE_HEIGHT
        total = sum(compute_subtree_height(c["id"]) for c in children)
        total += V_GAP * (len(children) - 1)
        return max(NODE_HEIGHT, total)

    def layout_node(node: dict, x: float, y: float, direction: int = 1):
        render_nodes.append(RenderNode(
            id=node["id"],
            parent_id=node.get("parent_id"),
            text=node.get("text", ""),
            level=node.get("level", 0),
            order=node.get("order", 0),
            side=node.get("side"),
            source_ids=node.get("source_ids", []),
            x=x,
            y=y,
            width=NODE_WIDTH,
            height=NODE_HEIGHT,
        ))

        children = children_map.get(node["id"], [])
        if not children:
            return

        total_height = sum(compute_subtree_height(c["id"]) for c in children)
        total_height += V_GAP * (len(children) - 1)

        child_x = x + direction * (NODE_WIDTH + H_GAP)
        child_y = y - total_height / 2

        for child in children:
            subtree_h = compute_subtree_height(child["id"])
            child_center_y = child_y + subtree_h / 2
            child["side"] = child.get("side") or node.get("side")
            layout_node(child, child_x, child_center_y, direction)
            render_edges.append(RenderEdge(
                id=f"e-{node['id']}-{child['id']}",
                source=node["id"],
                target=child["id"],
            ))
            child_y += subtree_h + V_GAP

    # Layout root at center
    root_x = 0.0
    root_y = 0.0

    render_nodes.append(RenderNode(
        id=root["id"],
        parent_id=None,
        text=root.get("text", title),
        level=0,
        order=0,
        side=None,
        source_ids=root.get("source_ids", []),
        x=root_x,
        y=root_y,
        width=NODE_WIDTH + 40,
        height=NODE_HEIGHT + 10,
    ))

    # Layout right-side branches
    right_children = [c for c in first_level if c.get("side") == "right"]
    left_children = [c for c in first_level if c.get("side") == "left"]

    def layout_side(children: list[dict], direction: int):
        if not children:
            return
        total_height = sum(compute_subtree_height(c["id"]) for c in children)
        total_height += V_GAP * (len(children) - 1)
        start_y = root_y - total_height / 2
        base_x = root_x + direction * (NODE_WIDTH / 2 + 40 + H_GAP)

        for child in children:
            subtree_h = compute_subtree_height(child["id"])
            center_y = start_y + subtree_h / 2
            layout_node(child, base_x, center_y, direction)
            render_edges.append(RenderEdge(
                id=f"e-{root['id']}-{child['id']}",
                source=root["id"],
                target=child["id"],
            ))
            start_y += subtree_h + V_GAP

    layout_side(right_children, 1)
    layout_side(left_children, -1)

    return RenderData(nodes=render_nodes, edges=render_edges).model_dump()
