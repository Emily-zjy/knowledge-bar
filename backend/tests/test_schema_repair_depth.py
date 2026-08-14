from app.services.ai_mindmap import _compute_tree_depth, _normalize_mind_map
from app.services.schema_repair import repair_mind_map


def test_schema_repair_reparents_nodes_beyond_requested_depth() -> None:
    raw = {
        "title": "Topic",
        "nodes": [
            {"id": "root", "parentId": None, "text": "Topic", "order": 0},
            {"id": "category", "parentId": "root", "text": "Category", "order": 0},
            {"id": "subtopic", "parentId": "category", "text": "Subtopic", "order": 0},
            {"id": "detail", "parentId": "subtopic", "text": "Detail", "order": 0},
            {"id": "example", "parentId": "detail", "text": "Example", "order": 0},
        ],
    }

    repaired = repair_mind_map(raw, max_depth=3)
    data = _normalize_mind_map(repaired.data, "Topic", max_depth=3)

    assert repaired.repaired is True
    assert repaired.repairs == ["reparented_2_over_depth_nodes"]
    assert _compute_tree_depth(data.nodes) == 3
    assert len(data.nodes) == 5
