"""
Generate evaluation_report.md from evaluation results JSON.

Usage:
    cd backend
    python -m evaluation.generate_report [results/eval_XXXXXXXX_XXXXXX.json]

If no path given, uses the latest file in results/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RESULTS_DIR = Path(__file__).resolve().parent / "results"
REPORT_PATH = Path(__file__).resolve().parent / "evaluation_report.md"


def load_latest_results(explicit_path: str | None = None) -> list[dict]:
    if explicit_path:
        p = Path(explicit_path)
    else:
        files = sorted(RESULTS_DIR.glob("eval_*.json"))
        if not files:
            print("ERROR: No results found. Run evaluation first.")
            sys.exit(1)
        p = files[-1]
    print(f"Loading results from: {p}")
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _pct(val: float) -> str:
    return f"{val * 100:.1f}%"


def generate_report(results: list[dict]) -> str:
    lines: list[str] = []
    w = lines.append

    total = len(results)
    passed = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    precisions = [r["precision"] for r in passed if r["precision"] > 0]
    recalls = [r["recall"] for r in passed if r["recall"] > 0]
    latencies = [r["total_latency_ms"] for r in passed if r["total_latency_ms"] > 0]

    avg_p = sum(precisions) / len(precisions) if precisions else 0
    avg_r = sum(recalls) / len(recalls) if recalls else 0
    avg_lat = sum(latencies) / len(latencies) if latencies else 0
    p95_lat = sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0
    max_lat = max(latencies) if latencies else 0

    all_fps = []
    total_nodes = 0
    for r in passed:
        all_fps.extend(r.get("false_positives", []))
        total_nodes += r["node_count"]
    fp_rate = len(all_fps) / total_nodes if total_nodes else 0

    # === Header ===
    w("# AI Agent Evaluation Report")
    w("")
    w("## 1. 测试集说明")
    w("")
    w(f"- 总 Case 数量: **{total}**")
    w(f"- 通过: **{len(passed)}** | 失败: **{len(failed)}**")
    w(f"- 成功率: **{_pct(len(passed)/total)}**")
    w("")

    by_cat: dict[str, list[dict]] = {}
    for r in results:
        by_cat.setdefault(r["test_category"], []).append(r)

    w("| 类别 | Case数 | 通过 | 失败 |")
    w("|------|--------|------|------|")
    for cat in sorted(by_cat.keys()):
        cat_r = by_cat[cat]
        cat_pass = sum(1 for r in cat_r if r["success"])
        w(f"| {cat} | {len(cat_r)} | {cat_pass} | {len(cat_r)-cat_pass} |")
    w("")

    # === 25 Case Results ===
    w("## 2. 25 Case 执行结果")
    w("")
    w("| Case | 标题 | 类别 | 状态 | 节点数 | 深度 | Precision | Recall | 延迟 |")
    w("|------|------|------|------|--------|------|-----------|--------|------|")
    for r in results:
        status = "✅" if r["success"] else "❌"
        lat = f"{r['total_latency_ms']:.0f}ms" if r["total_latency_ms"] else "N/A"
        p = f"{r['precision']:.2f}" if r["success"] else "-"
        rc = f"{r['recall']:.2f}" if r["success"] else "-"
        title_short = r["title"][:20]
        w(f"| {r['case_id']} | {title_short} | {r['test_category'][:10]} | {status} | {r['node_count']} | {r['depth']} | {p} | {rc} | {lat} |")
    w("")

    # === Precision ===
    w("## 3. Precision 指标")
    w("")
    w(f"**整体 Precision: {avg_p:.4f} ({_pct(avg_p)})**")
    w("")
    if precisions:
        w("| Case | Precision | False Positives |")
        w("|------|-----------|-----------------|")
        for r in passed:
            if r["precision"] > 0:
                fps_str = ", ".join(r.get("false_positives", [])[:5]) or "无"
                w(f"| {r['case_id']} | {r['precision']:.4f} | {fps_str} |")
        w("")

        low_p = [r for r in passed if r["precision"] < 0.5]
        if low_p:
            w("### 准确率偏低 Case 分析")
            w("")
            for r in low_p:
                w(f"- **{r['case_id']}** ({r['title'][:30]}): P={r['precision']:.2f}")
                w(f"  - 生成 {r['node_count']} 节点，其中误报: {', '.join(r.get('false_positives', [])[:5])}")
            w("")

    # === Recall ===
    w("## 4. Recall 指标")
    w("")
    w(f"**整体 Recall: {avg_r:.4f} ({_pct(avg_r)})**")
    w("")
    if recalls:
        w("| Case | Recall | 遗漏节点 |")
        w("|------|--------|----------|")
        for r in passed:
            if r["recall"] > 0:
                missed_str = ", ".join(r.get("missed_nodes", [])[:5]) or "无"
                w(f"| {r['case_id']} | {r['recall']:.4f} | {missed_str} |")
        w("")

        low_r = [r for r in passed if r["recall"] < 0.5]
        if low_r:
            w("### 召回率偏低 Case 分析")
            w("")
            for r in low_r:
                w(f"- **{r['case_id']}** ({r['title'][:30]}): R={r['recall']:.2f}")
                w(f"  - 遗漏: {', '.join(r.get('missed_nodes', [])[:8])}")
            w("")

    # === False Positive ===
    w("## 5. False Positive 指标")
    w("")
    w(f"**误伤率: {fp_rate:.4f} ({_pct(fp_rate)})**")
    w(f"- 总生成节点: {total_nodes}")
    w(f"- 误报节点数: {len(all_fps)}")
    w("")
    if all_fps:
        w("### 误报分类")
        w("")
        w("| 类型 | 数量 | 示例 |")
        w("|------|------|------|")
        w(f"| 虚构节点 | {len(all_fps)} | {', '.join(all_fps[:5])} |")
        w("")

    # === Bad Case Top 10 ===
    w("## 6. Bad Case Top 10")
    w("")
    bad_cases = sorted(
        [r for r in results if r["success"] and (r["precision"] < 0.6 or r["recall"] < 0.5)],
        key=lambda r: r["precision"] + r["recall"],
    )[:10]
    if not bad_cases:
        bad_cases = sorted(
            [r for r in results if not r["success"]],
            key=lambda r: r["case_id"],
        )[:10]

    if bad_cases:
        for i, r in enumerate(bad_cases, 1):
            w(f"### Bad Case #{i}: {r['case_id']} - {r['title'][:40]}")
            w("")
            w(f"- **问题类型**: {'生成失败' if not r['success'] else '质量不足'}")
            if r.get("error_code"):
                w(f"- **错误码**: {r['error_code']}")
                w(f"- **错误信息**: {r.get('error_message', '')[:80]}")
            w(f"- **Precision**: {r['precision']:.2f} | **Recall**: {r['recall']:.2f}")
            if r.get("false_positives"):
                w(f"- **错误节点**: {', '.join(r['false_positives'][:5])}")
            if r.get("missed_nodes"):
                w(f"- **遗漏节点**: {', '.join(r['missed_nodes'][:5])}")
            if r.get("evaluation_notes"):
                w(f"- **备注**: {'; '.join(r['evaluation_notes'][:3])}")
            w(f"- **优化建议**: {'调整Prompt增加约束' if r.get('false_positives') else '增加信息提取深度'}")
            w("")
    else:
        w("无显著 Bad Case。")
        w("")

    # === Latency ===
    w("## 7. Latency 分析")
    w("")
    w(f"| 指标 | 数值 |")
    w(f"|------|------|")
    w(f"| 平均延迟 | {avg_lat:.0f}ms |")
    w(f"| P95 延迟 | {p95_lat:.0f}ms |")
    w(f"| 最大延迟 | {max_lat:.0f}ms |")
    w(f"| 测试样本数 | {len(latencies)} |")
    w("")

    if latencies:
        w("### 各阶段延迟")
        w("")
        stage_totals: dict[str, list[float]] = {}
        for r in passed:
            for s in r.get("stages", []):
                stage_totals.setdefault(s["stage"], []).append(s["duration_ms"])

        if stage_totals:
            w("| 阶段 | 平均(ms) | P95(ms) | 失败次数 |")
            w("|------|----------|---------|----------|")
            for stage_name, durations in stage_totals.items():
                avg_d = sum(durations) / len(durations)
                sorted_d = sorted(durations)
                p95_d = sorted_d[int(len(sorted_d) * 0.95)] if sorted_d else 0
                fail_count = sum(1 for r in passed for s in r.get("stages", [])
                                 if s["stage"] == stage_name and not s["success"])
                w(f"| {stage_name} | {avg_d:.1f} | {p95_d:.1f} | {fail_count} |")
            w("")

    # === Failure Analysis ===
    w("## 8. 失败链路分析")
    w("")
    if failed:
        w(f"失败 Case 数量: {len(failed)}")
        w("")
        w("| Case | 错误码 | 错误信息 |")
        w("|------|--------|----------|")
        for r in failed:
            msg = (r.get("error_message") or "")[:60]
            w(f"| {r['case_id']} | {r.get('error_code', 'N/A')} | {msg} |")
        w("")

        error_codes: dict[str, int] = {}
        for r in failed:
            code = r.get("error_code", "UNKNOWN")
            error_codes[code] = error_codes.get(code, 0) + 1
        w("### 错误分布")
        w("")
        for code, count in sorted(error_codes.items(), key=lambda x: -x[1]):
            w(f"- `{code}`: {count} 次")
        w("")
    else:
        w("无失败 Case。")
        w("")

    # === Priority ===
    w("## 9. 问题优先级排序")
    w("")
    issues: list[tuple[str, str, str]] = []

    if len(failed) > 0:
        issues.append(("P0", "生成失败", f"{len(failed)} 个 Case 未能产出结果"))
    if avg_r < 0.6:
        issues.append(("P0", "召回率过低", f"平均 Recall {avg_r:.2f}，大量关键信息遗漏"))
    if avg_p < 0.5:
        issues.append(("P0", "准确率过低", f"平均 Precision {avg_p:.2f}，大量错误节点"))
    if fp_rate > 0.2:
        issues.append(("P1", "误伤率偏高", f"FP Rate {_pct(fp_rate)}，存在虚构内容"))
    if avg_lat > 10000:
        issues.append(("P1", "延迟过高", f"平均 {avg_lat:.0f}ms，影响用户体验"))
    if avg_r < 0.8 and avg_r >= 0.6:
        issues.append(("P2", "召回率可优化", f"平均 Recall {avg_r:.2f}"))
    if avg_p < 0.7 and avg_p >= 0.5:
        issues.append(("P2", "准确率可优化", f"平均 Precision {avg_p:.2f}"))

    if issues:
        w("| 优先级 | 问题 | 详情 |")
        w("|--------|------|------|")
        for pri, issue, detail in issues:
            w(f"| {pri} | {issue} | {detail} |")
    else:
        w("当前无显著质量问题。")
    w("")

    # === Optimization ===
    w("## 10. 下一版本优化建议")
    w("")
    w("### Prompt 优化")
    w("- 增加结构化输出约束（如要求覆盖所有 ## 章节标题）")
    w("- 针对数据类文本增加「保留原始数值」的指令")
    w("- 对模糊/缺失信息增加「不虚构」的强化约束")
    w("")
    w("### 工程优化")
    w("- 对超长文本实现分块摘要 → 合并策略")
    w("- 增加流式输出减少用户感知延迟")
    w("- 增加结果缓存避免重复生成")
    w("")
    w("### 评测体系迭代")
    w("- 引入人工标注 Ground Truth 对比")
    w("- 增加 A/B 测试框架对比 Prompt 版本")
    w("- 建立回归测试基线防止质量下降")
    w("")

    # === Composite Score ===
    w("## 综合评分")
    w("")
    # Recompute here
    bad_case_count = len([r for r in passed if r["precision"] < 0.5 or r["recall"] < 0.3])
    bad_case_ratio = bad_case_count / len(passed) if passed else 0

    p_score = avg_p * 15
    r_score = avg_r * 15
    fp_s = max(0, (1 - fp_rate * 5)) * 10
    bc_s = max(0, (1 - bad_case_ratio * 2)) * 10
    model_q = p_score + r_score + fp_s + bc_s

    lat_s = max(0, min(10, 10 - (avg_lat - 3000) / 1000)) if avg_lat < 13000 else 0
    stab_s = (len(passed) / total) * 10
    fail_s = max(0, (1 - (len(failed) / total) * 3)) * 10
    eng = lat_s + stab_s + fail_s

    notes_count = sum(len(r.get("evaluation_notes", [])) for r in passed)
    edit_r = notes_count / len(passed) if passed else 0
    edit_s = max(0, (1 - edit_r * 0.5)) * 10
    ux_issues = sum(1 for r in passed if r["node_count"] < 3 or r["depth"] < 2)
    ux_s = max(0, (1 - ux_issues / len(passed) * 2)) * 10 if passed else 0
    usab = edit_s + ux_s

    total_score = model_q + eng + usab

    w(f"| 维度 | 得分 | 满分 | 明细 |")
    w(f"|------|------|------|------|")
    w(f"| 模型质量 | {model_q:.1f} | 50 | P={p_score:.1f} R={r_score:.1f} FP={fp_s:.1f} BadCase={bc_s:.1f} |")
    w(f"| 工程体验 | {eng:.1f} | 30 | Latency={lat_s:.1f} 稳定={stab_s:.1f} 失败率={fail_s:.1f} |")
    w(f"| 产品可用性 | {usab:.1f} | 20 | 修改率={edit_s:.1f} UX={ux_s:.1f} |")
    w(f"| **总分** | **{total_score:.1f}** | **100** | |")
    w("")

    return "\n".join(lines)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    results = load_latest_results(path)
    report = generate_report(results)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\nReport generated: {REPORT_PATH}")
    print(f"Total cases: {len(results)}")


if __name__ == "__main__":
    main()
