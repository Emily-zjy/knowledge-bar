"""
Unified Binary Evaluation Pipeline - Phase 1: API Generation
Calls /api/mindmaps/generate for each of 15 cases, freezes task_id and full response.
Saves to run_binary/ directory.
"""
import json
import os
import sys
import time
import hashlib
import urllib.request
import urllib.error

BACKEND_URL = "http://127.0.0.1:8000"
ARTIFACTS_BASE = "d:/knowledge bar/artifacts/mindmap-trace-eval"
OUTPUT_DIR = os.path.join(ARTIFACTS_BASE, "run_binary")

sys.path.insert(0, "d:/knowledge bar/backend")
os.chdir("d:/knowledge bar/backend")

# Load test cases
ns = {}
exec(open("trace_eval.py", encoding="utf-8").read(), ns)
TEST_CASES = ns["TEST_CASES"]

os.makedirs(OUTPUT_DIR, exist_ok=True)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)


def api_post(endpoint, body, timeout=120):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{BACKEND_URL}{endpoint}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))


def api_get(endpoint, timeout=30):
    req = urllib.request.Request(f"{BACKEND_URL}{endpoint}", method="GET")
    resp = urllib.request.urlopen(req, timeout=timeout)
    return json.loads(resp.read().decode("utf-8"))


def run_case(case_id, case):
    print(f"\n{'='*60}")
    print(f"  {case_id}: {case['title']}")
    print(f"{'='*60}")

    case_dir = os.path.join(OUTPUT_DIR, case_id)
    os.makedirs(case_dir, exist_ok=True)

    text = case["text"]
    title = case.get("title", "")
    max_depth = 3 if case_id == "T10" else 4

    # S0: Record input
    s0 = {
        "case_id": case_id,
        "title": title,
        "char_count": len(text),
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    save_json(os.path.join(case_dir, "00-input.json"), s0)

    # Call API generate
    print(f"  [{case_id}] Calling /api/mindmaps/generate...")
    t0 = time.time()
    try:
        resp = api_post("/api/mindmaps/generate", {
            "text": text,
            "title": title,
            "max_depth": max_depth,
            "map_type": "auto",
        })
    except Exception as e:
        print(f"  [{case_id}] API FAILED: {e}")
        save_json(os.path.join(case_dir, "api-error.json"), {"error": str(e)})
        return None

    elapsed = time.time() - t0
    print(f"  [{case_id}] Done in {elapsed:.1f}s - task_id={resp.get('task_id')}")
    print(f"  [{case_id}] nodes={len(resp.get('nodes',[]))} edges={len(resp.get('edges',[]))}")

    # Save frozen response
    save_json(os.path.join(case_dir, "api-generate-response.json"), resp)

    task_id = resp.get("task_id")

    # S9D prep: verify GET returns same data while server is running
    try:
        get_resp = api_get(f"/api/mindmaps/{task_id}")
        save_json(os.path.join(case_dir, "api-get-response.json"), get_resp)
        print(f"  [{case_id}] GET verify: nodes={len(get_resp.get('nodes',[]))} edges={len(get_resp.get('edges',[]))}")
    except Exception as e:
        print(f"  [{case_id}] GET FAILED: {e}")
        save_json(os.path.join(case_dir, "api-get-error.json"), {"error": str(e)})

    # Extract and save S5/S6/S7 equivalent data from the frozen response
    frozen = {
        "task_id": task_id,
        "status": resp.get("status"),
        "title": resp.get("title"),
        "node_count": len(resp.get("nodes", [])),
        "edge_count": len(resp.get("edges", [])),
        "nodes": resp.get("nodes", []),
        "edges": resp.get("edges", []),
        "elapsed_s": elapsed,
    }
    save_json(os.path.join(case_dir, "frozen-data.json"), frozen)

    # Verify tree structure from frozen data
    nodes = resp.get("nodes", [])
    edges = resp.get("edges", [])
    node_ids = {n["id"] for n in nodes}

    # Check edges consistency
    edge_set = set()
    invalid_edges = []
    duplicate_edges = []
    self_loops = []
    for e in edges:
        key = f"{e['source']}->{e['target']}"
        if e["source"] not in node_ids or e["target"] not in node_ids:
            invalid_edges.append(e)
        if key in edge_set:
            duplicate_edges.append(e)
        if e["source"] == e["target"]:
            self_loops.append(e)
        edge_set.add(key)

    # Check parent_id → edge mapping
    parent_edges_expected = set()
    for n in nodes:
        if n.get("parent_id") and n["parent_id"] in node_ids:
            parent_edges_expected.add(f"{n['parent_id']}->{n['id']}")

    actual_edge_set = {f"{e['source']}->{e['target']}" for e in edges}
    missing_edges = parent_edges_expected - actual_edge_set
    extra_edges = actual_edge_set - parent_edges_expected

    s7_check = {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "expected_edges_from_parent_ids": len(parent_edges_expected),
        "invalid_edges": len(invalid_edges),
        "duplicate_edges": len(duplicate_edges),
        "self_loops": len(self_loops),
        "missing_edges": list(missing_edges)[:5],
        "extra_edges": list(extra_edges)[:5],
        "missing_edge_count": len(missing_edges),
        "extra_edge_count": len(extra_edges),
        "s7_pass": (len(invalid_edges) == 0 and len(duplicate_edges) == 0 and
                    len(self_loops) == 0 and len(missing_edges) == 0 and len(extra_edges) == 0),
    }
    save_json(os.path.join(case_dir, "s7-check.json"), s7_check)
    print(f"  [{case_id}] S7 check: pass={s7_check['s7_pass']} missing={len(missing_edges)} extra={len(extra_edges)}")

    return {"task_id": task_id, "frozen": frozen, "s7_check": s7_check}


def main():
    # Verify backend is up
    try:
        health = api_get("/health")
        print(f"Backend: {health}")
    except Exception as e:
        print(f"ERROR: Backend not reachable: {e}")
        sys.exit(1)

    results = {}
    for i in range(1, 16):
        cid = f"T{i:02d}"
        results[cid] = run_case(cid, TEST_CASES[cid])

    save_json(os.path.join(OUTPUT_DIR, "phase1-results.json"), results)
    print(f"\n{'='*60}")
    print(f"Phase 1 complete. Results in {OUTPUT_DIR}")

    # Summary
    success = sum(1 for r in results.values() if r is not None)
    s7_pass = sum(1 for r in results.values() if r and r.get("s7_check", {}).get("s7_pass"))
    print(f"API generation: {success}/15 succeeded")
    print(f"S7 structure check: {s7_pass}/15 passed")


if __name__ == "__main__":
    main()
