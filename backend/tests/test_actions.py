import pytest

from app.services.actions import chunk_text, prepare_text, render_mindmap, save_mindmap_draft, validate_mindmap


def test_prepare_text_basic_paragraphs():
    result = prepare_text(" First paragraph. \n\n Second paragraph. ")
    assert len(result["paragraphs"]) == 2
    assert result["paragraphs"][0]["text"] == "First paragraph."
    assert result["paragraphs"][1]["text"] == "Second paragraph."


def test_prepare_text_stable_ids():
    first = prepare_text("Hello world.\n\nSecond paragraph.")
    second = prepare_text("Hello world.\n\nSecond paragraph.")
    assert first["paragraphs"][0]["id"] == second["paragraphs"][0]["id"]


def test_chunk_text_multiple_chunks():
    paragraphs = [{"id": f"p-{index}", "text": "x" * 2000, "order": index} for index in range(5)]
    chunks = chunk_text(paragraphs, max_chunk_chars=5000)
    assert len(chunks) >= 2
    assert {pid for chunk in chunks for pid in chunk["paragraph_ids"]} == {f"p-{index}" for index in range(5)}


def _valid_nodes():
    return [
        {
            "id": "node-root",
            "parent_id": None,
            "text": "Learning Plan",
            "level": 0,
            "order": 0,
            "side": None,
            "source_ids": [],
        },
        {
            "id": "node-1",
            "parent_id": "node-root",
            "text": "Reading",
            "level": 1,
            "order": 1,
            "side": "right",
            "source_ids": ["p-1"],
        },
        {
            "id": "node-2",
            "parent_id": "node-root",
            "text": "Practice",
            "level": 1,
            "order": 2,
            "side": "left",
            "source_ids": ["p-2"],
        },
    ]


def test_save_mindmap_draft_rejects_long_text():
    nodes = [
        {"id": "node-root", "parent_id": None, "text": "A" * 200, "level": 0, "order": 0, "side": None, "source_ids": []}
    ]
    with pytest.raises(Exception):
        save_mindmap_draft("task-123", "Title", "auto", nodes)


def test_validate_mindmap_rejects_duplicate_ids():
    nodes = _valid_nodes()
    nodes.append({**nodes[1], "text": "Duplicate"})
    result = validate_mindmap(
        {"title": "Learning Plan", "map_type": "knowledge", "nodes": nodes},
        [{"id": "p-1", "text": "Reading notes", "order": 0}, {"id": "p-2", "text": "Practice notes", "order": 1}],
        max_depth=4,
    )
    assert result["passed"] is False
    assert any(error["code"] == "DUPLICATE_ID" for error in result["errors"])


def test_render_mindmap_edges_connect_correctly():
    result = render_mindmap({"title": "Learning Plan", "map_type": "knowledge", "nodes": _valid_nodes()})
    assert len(result["nodes"]) == 3
    assert len(result["edges"]) == 2
    assert {edge["source"] for edge in result["edges"]} == {"node-root"}
