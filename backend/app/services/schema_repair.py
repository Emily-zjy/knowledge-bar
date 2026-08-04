"""
Schema Repair Layer for Knowledge Bar Mind Map output.

Attempts to fix common structural issues in LLM-generated mind maps
before Pydantic validation rejects them. Only fixes structure, never
alters semantic content.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class RepairResult:
    def __init__(self, data: dict, repaired: bool, repairs: list[str]) -> None:
        self.data = data
        self.repaired = repaired
        self.repairs = repairs


def repair_mind_map(raw: dict, max_nodes: int = 25) -> RepairResult:
    """
    Attempt structural repairs on raw LLM output.
    Returns RepairResult with the (possibly fixed) data and a log of what was changed.
    """
    repairs: list[str] = []
    data = _deep_copy_dict(raw)

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return RepairResult(data, False, [])

    nodes = _fix_field_names(nodes, repairs)
    nodes = _fix_multiple_roots(nodes, repairs)
    nodes = _fix_invalid_parent_ids(nodes, repairs)
    nodes = _fix_node_count(nodes, max_nodes, repairs)
    nodes = _fix_text_length(nodes, repairs)
    nodes = _fix_missing_order(nodes, repairs)

    data["nodes"] = nodes
    return RepairResult(data, len(repairs) > 0, repairs)


def _deep_copy_dict(d: dict) -> dict:
    import json
    return json.loads(json.dumps(d))


def _fix_field_names(nodes: list[dict], repairs: list[str]) -> list[dict]:
    """Normalize common field name variants to the expected schema."""
    field_map = {
        "parent": "parentId",
        "parent_id": "parentId",
        "parentid": "parentId",
        "node_id": "id",
        "name": "text",
        "label": "text",
        "content": "text",
        "node_name": "text",
    }
    fixed = False
    for node in nodes:
        for wrong, correct in field_map.items():
            if wrong in node and correct not in node:
                node[correct] = node.pop(wrong)
                fixed = True
    if fixed:
        repairs.append("field_names_normalized")
    return nodes


def _fix_multiple_roots(nodes: list[dict], repairs: list[str]) -> list[dict]:
    """If multiple roots exist, keep the first and re-parent others under it."""
    roots = [n for n in nodes if n.get("parentId") is None or n.get("parentId") == ""]
    # Normalize empty string parentId to None
    for n in nodes:
        if n.get("parentId") == "":
            n["parentId"] = None

    roots = [n for n in nodes if n.get("parentId") is None]
    if len(roots) <= 1:
        return nodes

    primary_root = roots[0]
    root_id = primary_root.get("id", "node-root")
    max_order = max((n.get("order", 0) for n in nodes), default=0)

    for i, extra_root in enumerate(roots[1:], start=1):
        extra_root["parentId"] = root_id
        extra_root["order"] = max_order + i
        repairs.append(f"extra_root_reparented:{extra_root.get('id')}")

    return nodes


def _fix_invalid_parent_ids(nodes: list[dict], repairs: list[str]) -> list[dict]:
    """Fix nodes whose parentId points to a non-existent node."""
    known_ids = {n.get("id") for n in nodes if n.get("id")}
    root_id = None
    for n in nodes:
        if n.get("parentId") is None:
            root_id = n.get("id")
            break

    if not root_id:
        return nodes

    for node in nodes:
        pid = node.get("parentId")
        if pid is not None and pid not in known_ids:
            node["parentId"] = root_id
            repairs.append(f"invalid_parentId_fixed:{node.get('id')}:{pid}->{root_id}")

    return nodes


def _fix_node_count(nodes: list[dict], max_nodes: int, repairs: list[str]) -> list[dict]:
    """Trim excess nodes by removing deepest leaf nodes first."""
    if len(nodes) <= max_nodes:
        return nodes

    # Build parent->children map
    children_map: dict[str | None, list[dict]] = {}
    for n in nodes:
        children_map.setdefault(n.get("parentId"), []).append(n)

    # Calculate depth for each node
    id_to_node = {n.get("id"): n for n in nodes}
    depths: dict[str, int] = {}

    def get_depth(node_id: str, visited: set[str] | None = None) -> int:
        if visited is None:
            visited = set()
        if node_id in depths:
            return depths[node_id]
        if node_id in visited:
            return 0
        visited.add(node_id)
        node = id_to_node.get(node_id)
        if not node or node.get("parentId") is None:
            depths[node_id] = 0
            return 0
        parent_depth = get_depth(node["parentId"], visited)
        depths[node_id] = parent_depth + 1
        return depths[node_id]

    for n in nodes:
        nid = n.get("id")
        if nid:
            get_depth(nid)

    # Check which nodes are leaves
    parent_ids = {n.get("parentId") for n in nodes}

    # Sort by depth descending, remove deepest leaves first
    scored = []
    for n in nodes:
        nid = n.get("id")
        is_leaf = nid not in parent_ids
        depth = depths.get(nid, 0)
        scored.append((depth, is_leaf, n))

    # Keep root always, then sort rest by (not-leaf first, shallow first)
    root_nodes = [s for s in scored if s[2].get("parentId") is None]
    non_root = [s for s in scored if s[2].get("parentId") is not None]
    non_root.sort(key=lambda x: (-x[0], -int(x[1])))

    to_remove = len(nodes) - max_nodes
    removed_ids: set[str] = set()
    for depth, is_leaf, node in non_root:
        if to_remove <= 0:
            break
        if is_leaf or node.get("id") not in parent_ids:
            removed_ids.add(node.get("id", ""))
            to_remove -= 1

    result = [n for n in nodes if n.get("id") not in removed_ids]

    # Fix any orphaned children of removed nodes
    remaining_ids = {n.get("id") for n in result}
    root_id = next((n.get("id") for n in result if n.get("parentId") is None), None)
    for n in result:
        if n.get("parentId") and n["parentId"] not in remaining_ids:
            n["parentId"] = root_id

    if removed_ids:
        repairs.append(f"trimmed_{len(removed_ids)}_excess_nodes")

    return result


def _fix_text_length(nodes: list[dict], repairs: list[str]) -> list[dict]:
    """Truncate node text exceeding 120 chars."""
    fixed = False
    for node in nodes:
        text = node.get("text", "")
        if isinstance(text, str) and len(text) > 120:
            node["text"] = text[:117] + "..."
            fixed = True
    if fixed:
        repairs.append("text_truncated")
    return nodes


def _fix_missing_order(nodes: list[dict], repairs: list[str]) -> list[dict]:
    """Assign order field if missing."""
    needs_fix = any("order" not in n for n in nodes)
    if not needs_fix:
        return nodes

    for i, node in enumerate(nodes):
        if "order" not in node:
            node["order"] = i
    repairs.append("order_assigned")
    return nodes
