"""
MindMap Trace Engine - Executes S0-S7 pipeline stages and saves traces.
Imports test cases from trace_eval.py.
"""
import hashlib
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
os.chdir(str(Path(__file__).parent))

from app.services.actions import prepare_text, chunk_text, save_mindmap_draft, validate_mindmap, render_mindmap
from app.models.mindmap import GenerateRequest

MAX_RETRY = 2
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
ARTIFACTS_DIR = Path(__file__).parent.parent / "artifacts" / "mindmap-trace-eval" / RUN_ID


def ensure_case_dir(case_id):
    d = ARTIFACTS_DIR / case_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def compute_sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_s0_input(case_id, case, case_dir):
    result = {
        "case_id": case_id,
        "title": case["title"],
        "char_count": len(case["text"]),
        "sha256": compute_sha256(case["text"]),
        "text_preview": case["text"][:200],
    }
    save_json(case_dir / "00-input.json", result)
    return result


def run_s1_request_ingress(case_id, case, case_dir):
    request_body = {
        "text": case["text"],
        "title": case.get("title"),
        "max_depth": 4,
        "map_type": "auto",
    }
    backend_received = GenerateRequest(**request_body)

    frontend_hash = compute_sha256(case["text"])
    backend_hash = compute_sha256(backend_received.text)

    result = {
        "case_id": case_id,
        "frontend_text_hash": frontend_hash,
        "backend_text_hash": backend_hash,
        "hash_match": frontend_hash == backend_hash,
        "frontend_char_count": len(case["text"]),
        "backend_char_count": len(backend_received.text),
        "char_count_match": len(case["text"]) == len(backend_received.text),
        "params_match": True,
        "title": backend_received.title,
        "max_depth": backend_received.max_depth,
        "map_type": backend_received.map_type,
    }
    save_json(case_dir / "01-request-ingress.json", result)
    return result


def run_s2_prepare_text(case_id, case, case_dir):
    prepared = prepare_text(case["text"])
    result = {
        "case_id": case_id,
        "clean_text_chars": len(prepared["clean_text"]),
        "original_chars": len(case["text"]),
        "paragraph_count": len(prepared["paragraphs"]),
        "needs_chunking": prepared["needs_chunking"],
        "paragraphs": prepared["paragraphs"],
        "clean_text_preview": prepared["clean_text"][:300],
    }
    save_json(case_dir / "02-prepared-text.json", result)
    return result


def run_s3_chunk_text(case_id, prepared, case_dir):
    paragraphs = prepared["paragraphs"]

    if prepared.get("needs_chunking", False):
        chunks = chunk_text(paragraphs)
    else:
        chunks = [{
            "chunk_index": 0,
            "paragraph_ids": [p["id"] for p in paragraphs],
            "text": "\n\n".join(p["text"] for p in paragraphs),
        }]

    all_para_ids = set(p["id"] for p in paragraphs)
    covered_ids = set()
    for chunk in chunks:
        for pid in chunk["paragraph_ids"]:
            covered_ids.add(pid)

    coverage = len(covered_ids) / len(all_para_ids) if all_para_ids else 1.0

    all_chunk_para_ids = []
    for chunk in chunks:
        all_chunk_para_ids.extend(chunk["paragraph_ids"])
    has_duplicates = len(all_chunk_para_ids) != len(set(all_chunk_para_ids))

    original_order = [p["id"] for p in paragraphs]
    chunk_order = all_chunk_para_ids
    is_ordered = chunk_order == [pid for pid in original_order if pid in set(chunk_order)]

    result = {
        "case_id": case_id,
        "chunk_count": len(chunks),
        "total_paragraphs": len(paragraphs),
        "covered_paragraphs": len(covered_ids),
        "coverage": coverage,
        "has_duplicates": has_duplicates,
        "is_ordered": is_ordered,
        "chunks_summary": [
            {"index": c["chunk_index"], "para_count": len(c["paragraph_ids"]), "chars": len(c["text"])}
            for c in chunks
        ],
    }
    save_json(case_dir / "03-chunks.json", result)
    return result


def run_s4_llm_generate(case_id, case, paragraphs, case_dir):
    from app.services.mindmap_agent import _generate_with_llm

    title = case.get("title", "")
    max_depth = 4
    map_type = "auto"

    if case_id == "T10":
        max_depth = 3

    try:
        raw_result = _generate_with_llm(
            paragraphs=paragraphs,
            title=title,
            max_depth=max_depth,
            map_type=map_type,
        )
        result = {
            "case_id": case_id,
            "success": True,
            "title": raw_result.get("title", ""),
            "node_count": len(raw_result.get("nodes", [])),
            "nodes": raw_result.get("nodes", []),
            "map_type": raw_result.get("map_type", ""),
            "model": os.environ.get("AI_MODEL", "unknown"),
        }
    except Exception as e:
        result = {
            "case_id": case_id,
            "success": False,
            "error": str(e),
            "model": os.environ.get("AI_MODEL", "unknown"),
        }

    save_json(case_dir / "04-llm-raw-response.json", result)
    return result


def run_s5_draft_parser(case_id, llm_result, case_dir):
    if not llm_result.get("success"):
        result = {
            "case_id": case_id,
            "success": False,
            "error": "S4 failed, cannot parse",
            "nodes_from_llm": 0,
            "nodes_parsed": 0,
        }
        save_json(case_dir / "05-draft.json", result)
        return result

    nodes = llm_result.get("nodes", [])
    title = llm_result.get("title", "untitled")
    map_type = llm_result.get("map_type", "auto")

    try:
        draft_result = save_mindmap_draft(
            task_id="trace-" + case_id,
            title=title,
            map_type=map_type,
            nodes=nodes,
        )
        parsed_nodes = draft_result["draft"]["nodes"]
        result = {
            "case_id": case_id,
            "success": True,
            "nodes_from_llm": len(nodes),
            "nodes_parsed": len(parsed_nodes),
            "nodes_lost": len(nodes) - len(parsed_nodes),
            "draft": draft_result["draft"],
            "parse_errors": [],
        }
    except Exception as e:
        result = {
            "case_id": case_id,
            "success": False,
            "error": str(e),
            "nodes_from_llm": len(nodes),
            "nodes_parsed": 0,
            "nodes_lost": len(nodes),
        }

    save_json(case_dir / "05-draft.json", result)
    return result


def run_s6_validate_repair(case_id, draft_result, paragraphs, case_dir):
    if not draft_result.get("success"):
        result = {
            "case_id": case_id,
            "success": False,
            "error": "S5 failed",
            "passed": False,
            "retry_count": 0,
            "final_draft": None,
            "final_validation": {"passed": False, "score": 0, "errors": [], "warnings": []},
        }
        save_json(case_dir / "06-validation-rounds.json", result)
        return result

    draft_data = draft_result["draft"]
    max_depth = 4
    if case_id == "T10":
        max_depth = 3

    validation = validate_mindmap(draft_data, paragraphs, max_depth)
    rounds = [{"round": 0, "validation": validation}]

    retry_count = 0
    final_draft = draft_data
    while not validation["passed"] and retry_count < MAX_RETRY:
        retry_count += 1
        try:
            from app.services.mindmap_agent import _fix_with_llm
            fixed_result = _fix_with_llm(
                errors=validation["errors"],
                warnings=validation["warnings"],
                current_nodes=final_draft["nodes"],
                paragraphs=paragraphs,
                max_depth=max_depth,
                map_type=final_draft.get("map_type", "auto"),
            )
            new_draft = save_mindmap_draft(
                task_id="trace-" + case_id + "-fix" + str(retry_count),
                title=fixed_result.get("title", final_draft["title"]),
                map_type=fixed_result.get("map_type", "auto"),
                nodes=fixed_result.get("nodes", []),
            )
            final_draft = new_draft["draft"]
            validation = validate_mindmap(final_draft, paragraphs, max_depth)
            rounds.append({"round": retry_count, "validation": validation})
        except Exception as e:
            rounds.append({"round": retry_count, "error": str(e)})
            break

    result = {
        "case_id": case_id,
        "success": True,
        "passed": validation["passed"],
        "final_score": validation.get("score", 0),
        "retry_count": retry_count,
        "error_count": len(validation.get("errors", [])),
        "warning_count": len(validation.get("warnings", [])),
        "rounds": rounds,
        "final_draft": final_draft,
        "final_validation": validation,
    }
    save_json(case_dir / "06-validation-rounds.json", result)
    return result


def run_s7_graph_builder(case_id, validate_result, case_dir):
    if validate_result.get("final_draft"):
        draft_data = validate_result["final_draft"]
    else:
        result = {
            "case_id": case_id,
            "success": False,
            "error": "No draft available for rendering",
            "node_count": 0,
            "edge_count": 0,
            "expected_edges": 0,
            "nodes": [],
            "edges": [],
        }
        save_json(case_dir / "07-graph.json", result)
        return result

    try:
        render_data = render_mindmap(draft_data)
        nodes = render_data.get("nodes", [])
        edges = render_data.get("edges", [])

        node_ids = {n["id"] for n in nodes}
        valid_edges = [e for e in edges if e["source"] in node_ids and e["target"] in node_ids]
        invalid_edges = [e for e in edges if e["source"] not in node_ids or e["target"] not in node_ids]

        edge_keys = set()
        duplicate_edges = []
        for edge in edges:
            key = edge["source"] + "->" + edge["target"]
            if key in edge_keys:
                duplicate_edges.append(edge)
            edge_keys.add(key)

        self_loops = [e for e in edges if e["source"] == e["target"]]
        expected_edges = max(0, len(nodes) - 1)

        result = {
            "case_id": case_id,
            "success": True,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "expected_edges": expected_edges,
            "valid_edges": len(valid_edges),
            "invalid_edges": len(invalid_edges),
            "duplicate_edges": len(duplicate_edges),
            "self_loops": len(self_loops),
            "nodes": nodes,
            "edges": edges,
        }
    except Exception as e:
        result = {
            "case_id": case_id,
            "success": False,
            "error": str(e),
            "node_count": 0,
            "edge_count": 0,
            "expected_edges": 0,
            "nodes": [],
            "edges": [],
        }

    save_json(case_dir / "07-graph.json", result)
    return result


def run_single_case(case_id, case):
    print("\n" + "=" * 60)
    print("  Running " + case_id + ": " + case["title"])
    print("=" * 60)

    case_dir = ensure_case_dir(case_id)
    trace = {"case_id": case_id, "title": case["title"], "stages": {}}

    # S0
    print("  [" + case_id + "] S0 TestInput...")
    s0 = run_s0_input(case_id, case, case_dir)
    trace["stages"]["S0"] = {"status": "done", "char_count": s0["char_count"]}

    # S1
    print("  [" + case_id + "] S1 RequestIngress...")
    s1 = run_s1_request_ingress(case_id, case, case_dir)
    trace["stages"]["S1"] = {"status": "done", "hash_match": s1["hash_match"]}

    # S2
    print("  [" + case_id + "] S2 PrepareText...")
    s2 = run_s2_prepare_text(case_id, case, case_dir)
    trace["stages"]["S2"] = {"status": "done", "paragraphs": s2["paragraph_count"]}

    # S3
    print("  [" + case_id + "] S3 ChunkText...")
    s3 = run_s3_chunk_text(case_id, s2, case_dir)
    trace["stages"]["S3"] = {"status": "done", "coverage": s3["coverage"]}

    # S4
    print("  [" + case_id + "] S4 LLMGenerate... (calling AI)")
    t0 = time.time()
    s4 = run_s4_llm_generate(case_id, case, s2["paragraphs"], case_dir)
    llm_time = time.time() - t0
    s4_status = "done" if s4.get("success") else "failed"
    trace["stages"]["S4"] = {"status": s4_status, "time_s": round(llm_time, 1), "nodes": s4.get("node_count", 0)}
    if s4.get("success"):
        print("  [" + case_id + "] S4 OK in " + str(round(llm_time, 1)) + "s, nodes=" + str(s4.get("node_count", 0)))
    else:
        print("  [" + case_id + "] S4 FAILED: " + s4.get("error", "unknown"))

    # S5
    print("  [" + case_id + "] S5 DraftParser...")
    s5 = run_s5_draft_parser(case_id, s4, case_dir)
    s5_status = "done" if s5.get("success") else "failed"
    trace["stages"]["S5"] = {"status": s5_status, "nodes_parsed": s5.get("nodes_parsed", 0)}

    # S6
    print("  [" + case_id + "] S6 ValidateRepair...")
    if s5.get("success"):
        t0 = time.time()
        s6 = run_s6_validate_repair(case_id, s5, s2["paragraphs"], case_dir)
        fix_time = time.time() - t0
        trace["stages"]["S6"] = {
            "status": "done",
            "passed": s6.get("passed"),
            "retries": s6.get("retry_count", 0),
            "time_s": round(fix_time, 1),
        }
        print("  [" + case_id + "] S6 passed=" + str(s6.get("passed")) + " retries=" + str(s6.get("retry_count", 0)))
    else:
        s6 = {
            "case_id": case_id, "success": False, "passed": False,
            "final_draft": None, "retry_count": 0,
            "final_validation": {"passed": False, "score": 0, "errors": [], "warnings": []},
        }
        save_json(case_dir / "06-validation-rounds.json", s6)
        trace["stages"]["S6"] = {"status": "failed", "passed": False}

    # S7
    print("  [" + case_id + "] S7 GraphBuilder...")
    s7 = run_s7_graph_builder(case_id, s6, case_dir)
    s7_status = "done" if s7.get("success") else "failed"
    trace["stages"]["S7"] = {
        "status": s7_status,
        "nodes": s7.get("node_count", 0),
        "edges": s7.get("edge_count", 0),
    }
    print("  [" + case_id + "] S7 nodes=" + str(s7.get("node_count", 0)) + " edges=" + str(s7.get("edge_count", 0)))

    save_json(case_dir / "trace-summary.json", trace)
    return trace


def run_batch(case_ids, test_cases):
    results = {}
    for cid in case_ids:
        if cid not in test_cases:
            print("WARNING: " + cid + " not found")
            continue
        results[cid] = run_single_case(cid, test_cases[cid])
    return results


if __name__ == "__main__":
    # Load test cases from trace_eval.py
    ns = {}
    exec(open("trace_eval.py", encoding="utf-8").read(), ns)
    TEST_CASES = ns["TEST_CASES"]

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=int, default=0,
                        help="1=T01-T05, 2=T06-T10, 3=T11-T15, 0=all")
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    if args.batch == 1:
        cases = ["T01", "T02", "T03", "T04", "T05"]
    elif args.batch == 2:
        cases = ["T06", "T07", "T08", "T09", "T10"]
    elif args.batch == 3:
        cases = ["T11", "T12", "T13", "T14", "T15"]
    else:
        cases = ["T" + str(i).zfill(2) for i in range(1, 16)]

    print("Run ID: " + RUN_ID)
    print("Artifacts: " + str(ARTIFACTS_DIR))
    print("Running: " + str(cases))
    print("Model: " + os.environ.get("AI_MODEL", "from .env"))

    results = run_batch(cases, TEST_CASES)

    save_json(ARTIFACTS_DIR / ("batch-" + str(args.batch) + "-summary.json"), results)
    print("\n" + "=" * 60)
    print("Batch " + str(args.batch) + " complete. Results in " + str(ARTIFACTS_DIR))
    print("=" * 60)
