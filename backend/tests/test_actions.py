"""Unit tests for mind map actions."""

import pytest

from app.services.actions import (
    chunk_text,
    prepare_text,
    render_mindmap,
    save_mindmap_draft,
    validate_mindmap,
)


class TestPrepareText:
    def test_basic_paragraphs(self):
        text = "第一段内容。\n\n第二段内容。\n\n第三段内容。"
        result = prepare_text(text)
        assert "paragraphs" in result
        assert len(result["paragraphs"]) == 3
        assert result["paragraphs"][0]["text"] == "第一段内容。"
        assert result["paragraphs"][1]["text"] == "第二段内容。"

    def test_stable_ids(self):
        text = "Hello world.\n\nSecond paragraph."
        r1 = prepare_text(text)
        r2 = prepare_text(text)
        assert r1["paragraphs"][0]["id"] == r2["paragraphs"][0]["id"]
        assert r1["paragraphs"][1]["id"] == r2["paragraphs"][1]["id"]

    def test_strips_whitespace(self):
        text = "   some text   \n\n   another  "
        result = prepare_text(text)
        assert result["paragraphs"][0]["text"] == "some text"
        assert result["paragraphs"][1]["text"] == "another"

    def test_empty_text(self):
        result = prepare_text("")
        assert result["paragraphs"] == []

    def test_needs_chunking_flag(self):
        short = "Short text."
        result = prepare_text(short)
        assert result["needs_chunking"] is False

        long_text = ("这是一个很长的段落内容。" * 50 + "\n\n") * 20
        result = prepare_text(long_text)
        assert result["needs_chunking"] is True


class TestChunkText:
    def test_single_chunk(self):
        paragraphs = [
            {"id": "p-1", "text": "Short text.", "index": 0}
        ]
        chunks = chunk_text(paragraphs, max_chunk_chars=6000)
        assert len(chunks) == 1
        assert chunks[0]["paragraph_ids"] == ["p-1"]

    def test_multiple_chunks(self):
        paragraphs = [
            {"id": f"p-{i}", "text": "x" * 2000, "index": i}
            for i in range(5)
        ]
        chunks = chunk_text(paragraphs, max_chunk_chars=5000)
        assert len(chunks) >= 2
        all_ids = []
        for c in chunks:
            all_ids.extend(c["paragraph_ids"])
        assert set(all_ids) == {f"p-{i}" for i in range(5)}


class TestSaveMindmapDraft:
    def test_valid_draft(self):
        nodes = [
            {"id": "node-root", "parent_id": None, "text": "Root", "level": 0, "order": 0, "side": None, "source_ids": []},
            {"id": "node-1", "parent_id": "node-root", "text": "Child A", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
        ]
        result = save_mindmap_draft("task-123", "Test Title", "knowledge", nodes)
        assert result["draft"]["title"] == "Test Title"
        assert result["draft"]["map_type"] == "knowledge"
        assert len(result["draft"]["nodes"]) == 2

    def test_rejects_long_text(self):
        nodes = [
            {"id": "node-root", "parent_id": None, "text": "A" * 200, "level": 0, "order": 0, "side": None, "source_ids": []},
        ]
        with pytest.raises(Exception):
            save_mindmap_draft("task-123", "Title", "auto", nodes)


class TestValidateMindmap:
    def _valid_draft(self):
        return {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-root", "parent_id": None, "text": "测试主题名称", "level": 0, "order": 0, "side": None, "source_ids": []},
                {"id": "node-1", "parent_id": "node-root", "text": "分支一内容", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-2", "parent_id": "node-root", "text": "分支二内容", "level": 1, "order": 2, "side": "left", "source_ids": ["p-2"]},
                {"id": "node-3", "parent_id": "node-root", "text": "分支三内容", "level": 1, "order": 3, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-4", "parent_id": "node-root", "text": "分支四内容", "level": 1, "order": 4, "side": "left", "source_ids": ["p-2"]},
                {"id": "node-5", "parent_id": "node-1", "text": "二级节点一", "level": 2, "order": 1, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-6", "parent_id": "node-1", "text": "二级节点二", "level": 2, "order": 2, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-7", "parent_id": "node-2", "text": "二级节点三", "level": 2, "order": 1, "side": "left", "source_ids": ["p-2"]},
                {"id": "node-8", "parent_id": "node-2", "text": "二级节点四", "level": 2, "order": 2, "side": "left", "source_ids": ["p-2"]},
                {"id": "node-9", "parent_id": "node-3", "text": "二级节点五", "level": 2, "order": 1, "side": "right", "source_ids": ["p-1"]},
            ],
        }

    def _paragraphs(self):
        return [
            {"id": "p-1", "text": "这是第一个段落的内容，包含足够多的文字来满足长度要求，确保验证能够正确通过所有检查项。" * 3, "index": 0},
            {"id": "p-2", "text": "这是第二个段落的内容，同样包含足够多的文字来确保通过源文本长度校验检查，这里补充更多内容。" * 3, "index": 1},
        ]

    def test_valid_passes(self):
        result = validate_mindmap(self._valid_draft(), self._paragraphs(), max_depth=4)
        assert result["passed"] is True
        assert result["score"] == 100

    def test_no_root_fails(self):
        draft = {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-1", "parent_id": "node-root", "text": "分支", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
            ],
        }
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert result["passed"] is False
        assert any(e["code"] == "NO_ROOT" for e in result["errors"])

    def test_duplicate_ids_fails(self):
        draft = self._valid_draft()
        draft["nodes"].append(
            {"id": "node-1", "parent_id": "node-root", "text": "重复分支", "level": 1, "order": 5, "side": "left", "source_ids": ["p-1"]}
        )
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert result["passed"] is False
        assert any(e["code"] == "DUPLICATE_ID" for e in result["errors"])

    def test_orphan_node_fails(self):
        draft = self._valid_draft()
        draft["nodes"].append(
            {"id": "node-orphan", "parent_id": "node-missing", "text": "孤立节点", "level": 2, "order": 1, "side": "right", "source_ids": ["p-1"]}
        )
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert result["passed"] is False
        error_codes = [e["code"] for e in result["errors"]]
        assert "INVALID_PARENT" in error_codes or "ORPHAN" in error_codes

    def test_exceeds_depth_fails(self):
        draft = self._valid_draft()
        # Add depth beyond max_depth=2: root(0)->node-1(1)->node-5(2)->deep(3)
        draft["nodes"].append(
            {"id": "node-deep", "parent_id": "node-5", "text": "超深节点", "level": 3, "order": 1, "side": "right", "source_ids": ["p-1"]}
        )
        result = validate_mindmap(draft, self._paragraphs(), max_depth=2)
        assert result["passed"] is False
        assert any(e["code"] == "EXCEEDS_DEPTH" for e in result["errors"])

    def test_invalid_source_ids_warning(self):
        draft = self._valid_draft()
        draft["nodes"][1]["source_ids"] = ["p-nonexist"]
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert any(w["code"] == "INVALID_SOURCE" for w in result["warnings"])

    def test_placeholder_node_fails(self):
        draft = self._valid_draft()
        draft["nodes"][1]["text"] = "核心概念"
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert result["passed"] is False
        assert any(e["code"] == "PLACEHOLDER_NODE" for e in result["errors"])

    def test_generic_title_fails(self):
        draft = self._valid_draft()
        draft["nodes"][0]["text"] = "知识导图"
        result = validate_mindmap(draft, self._paragraphs(), max_depth=4)
        assert result["passed"] is False
        assert any(e["code"] == "GENERIC_TITLE" for e in result["errors"])


class TestRenderMindmap:
    def test_basic_render(self):
        draft = {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-root", "parent_id": None, "text": "主题", "level": 0, "order": 0, "side": None, "source_ids": []},
                {"id": "node-1", "parent_id": "node-root", "text": "右侧", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-2", "parent_id": "node-root", "text": "左侧", "level": 1, "order": 2, "side": "left", "source_ids": ["p-2"]},
            ],
        }
        result = render_mindmap(draft)
        assert "nodes" in result
        assert "edges" in result
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2

        root = next(n for n in result["nodes"] if n["id"] == "node-root")
        assert root["x"] is not None
        assert root["y"] is not None
        assert root["width"] > 0
        assert root["height"] > 0

    def test_edges_connect_correctly(self):
        draft = {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-root", "parent_id": None, "text": "主题", "level": 0, "order": 0, "side": None, "source_ids": []},
                {"id": "node-1", "parent_id": "node-root", "text": "A分支", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
            ],
        }
        result = render_mindmap(draft)
        edge = result["edges"][0]
        assert edge["source"] == "node-root"
        assert edge["target"] == "node-1"

    def test_no_duplicate_edges(self):
        draft = {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-root", "parent_id": None, "text": "中心", "level": 0, "order": 0, "side": None, "source_ids": []},
                {"id": "node-1", "parent_id": "node-root", "text": "右一", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
                {"id": "node-2", "parent_id": "node-root", "text": "左一", "level": 1, "order": 2, "side": "left", "source_ids": ["p-2"]},
                {"id": "node-3", "parent_id": "node-1", "text": "子节点", "level": 2, "order": 1, "side": "right", "source_ids": ["p-1"]},
            ],
        }
        result = render_mindmap(draft)
        edge_ids = [e["id"] for e in result["edges"]]
        assert len(edge_ids) == len(set(edge_ids)), f"Duplicate edges found: {edge_ids}"
        assert len(result["edges"]) == 3

    def test_no_self_loop_edges(self):
        draft = {
            "title": "Test",
            "map_type": "auto",
            "nodes": [
                {"id": "node-root", "parent_id": None, "text": "中心", "level": 0, "order": 0, "side": None, "source_ids": []},
                {"id": "node-1", "parent_id": "node-root", "text": "分支", "level": 1, "order": 1, "side": "right", "source_ids": ["p-1"]},
            ],
        }
        result = render_mindmap(draft)
        for edge in result["edges"]:
            assert edge["source"] != edge["target"], f"Self-loop edge: {edge}"
