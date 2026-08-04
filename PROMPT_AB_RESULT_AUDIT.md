# Prompt A/B Test — 实验结果完整性审计

## 审计数据源

| 文件 | 路径 | 用途 |
|------|------|------|
| 全量实验原始 JSON | `backend/evaluation/results/prompt_ab_20260804_153616.json` | Pilot + Full 原始运行数据 |
| Pilot 实验原始 JSON | `backend/evaluation/results/prompt_ab_20260804_152817.json` | Pilot 独立运行数据 |
| 主测试集 | `backend/evaluation/test_cases.json` | 25 条测试定义 |
| 人工 Golden Dataset | `backend/evaluation/golden_dataset.json` | 9 条人工标注 |
| Stress Dataset | `backend/evaluation/reliability/stress_dataset.json` | 32 条压力测试 |
| 被审计报告 | `PROMPT_AB_EXPERIMENT_REPORT.md`, `PROMPT_AB_FULL_RESULT.md` | 实验结论文档 |

## 原始结果重新计算

### 基础计数

| 指标 | 原始 JSON 计算值 |
|------|------------------|
| V1 总运行数 | 75 |
| V2 总运行数 | 75 |
| Full API 调用 | 150 |
| Pilot API 调用 | 36 |
| **总 API 调用** | **186** |
| V1 成功运行 | 72/75 |
| V2 成功运行 | 75/75 |
| 总失败运行 | 3 (全部为 V1 T13) |
| 每 Case 运行次数 | 3 (全部一致) |
| 失败详情 | T13 run1/2/3: LLM_NETWORK_ERROR |

### 逐 Case 胜负统计（从原始 JSON 重新计算）

判定规则：取每 Case 各运行成功且 Precision > 0 的均值比较，差值绝对值 < 0.001 为平局。

| Case | V1 Avg P | V2 Avg P | Delta | 胜者 |
|------|----------|----------|-------|------|
| T01 | 0.5000 | 0.5789 | +0.079 | V2 |
| T02 | 0.6111 | 0.9375 | +0.327 | V2 |
| T03 | 0.5263 | 0.6930 | +0.167 | V2 |
| T04 | 0.5024 | 0.7353 | +0.233 | V2 |
| T05 | 0.4231 | 0.6667 | +0.244 | V2 |
| T06 | 0.5417 | 0.5417 | +0.000 | Tie |
| T07 | 0.6667 | 0.6667 | +0.000 | Tie |
| T08 | 0.5652 | 0.5824 | +0.017 | V2 |
| T09 | 0.5370 | 0.8194 | +0.282 | V2 |
| T10 | 0.4583 | 0.6667 | +0.208 | V2 |
| T11 | 0.4074 | 0.4706 | +0.064 | V2 |
| T12 | 0.5897 | 0.5897 | +0.000 | Tie |
| T13 | 0.0000* | 0.4815 | +0.482 | V2 |
| T14 | 0.4167 | 0.5385 | +0.121 | V2 |
| T15 | 0.5263 | 0.5897 | +0.063 | V2 |
| T16 | 0.7764 | 0.7273 | -0.048 | V1 |
| T17 | 0.4148 | 0.4706 | +0.056 | V2 |
| T18 | 0.4412 | 0.5013 | +0.061 | V2 |
| T19 | 0.3529 | 0.5714 | +0.218 | V2 |
| T20 | 0.5046 | 0.6154 | +0.110 | V2 |
| T21 | 0.4167 | 0.4167 | +0.000 | Tie |
| T22 | 0.4510 | 0.4783 | +0.027 | V2 |
| T23 | 0.3500 | 1.0000 | +0.650 | V2 |
| T24 | 0.0000** | 0.0000** | +0.000 | Tie |
| T25 | 0.6667 | 0.7500 | +0.083 | V2 |

*T13: V1 三次运行全部失败（无有效 Precision）
**T24: 空内容测试，expected_nodes = 0，两版本均正确返回 0 节点

**汇总：V2 胜出 19 | V1 胜出 1 | 平局 5 | 合计 25**

### 聚合指标重新计算

| 指标 | V1 (从 JSON) | V2 (从 JSON) | 报告值 V1 | 报告值 V2 | 一致性 |
|------|-------------|-------------|-----------|-----------|--------|
| Success Rate | 96.00% | 100.00% | 96.00% | 100.00% | ✓ |
| Avg Precision | 0.5063 | 0.6287 | 0.5063 | 0.6287 | ✓ |
| Median Precision | 0.5000 | 0.6000 | 0.5000 | 0.6000 | ✓ |
| Avg Recall | 0.9906 | 0.9965 | 0.9906 | 0.9965 | ✓ |
| FP Rate | 0.4892 | 0.4279 | 0.4892 | 0.4279 | ✓ |
| Avg Node Count | 19.99 | 16.73 | 20.0 | 16.7 | ✓ (四舍五入) |
| Node Range Pass | 40.74% | 88.89% | 40.74% | 88.89% | ✓ |
| Avg Latency | 12,588ms | 11,722ms | 12,588ms | 11,722ms | ✓ |
| P50 Latency | 11,390ms | 11,051ms | 11,390ms | 11,051ms | ✓ |
| P95 Latency | 24,472ms | 20,400ms | 24,472ms | 20,400ms | ✓ |
| Precision Lift | — | 1.2417x | — | 1.24x | ✓ |
| Forbidden | 0 | 0 | 0 | 0 | ✓ |

## 发现的不一致

### 疑点 1（已确认）：V2 胜负数量错误

| | 报告原值 | 实际值 | 修正 |
|--|---------|--------|------|
| V2 wins | 18 | **19** | +1 |
| Tie | 5 | 5 | — |
| V1 wins | 1 | 1 | — |
| 合计 | 24 ❌ | **25** ✓ | 差 1 |

原因：报告漏计 T13（V1 全部失败，V2 成功 → V2 胜），或 T01 被错误归为 Tie。从原始数据确认 T01 delta=+0.079 属于 V2 胜。

### 疑点 2（已确认）：T24 描述错误

| | 报告原文 | 实际定义 |
|--|---------|---------|
| T24 | "prompt injection test case" | **空内容测试（仅有标题无正文）** |
| T25 | 未明确区分 | **注入式攻击文本** |

T24 title = "空内容 - 仅有标题无正文"，expected_nodes = 0
T25 title = "异常输入 - 注入式攻击文本"，expected_nodes = 6（数据库索引）

### 疑点 3（已确认）：数据集命名混淆

| | 报告原文 | 实际情况 |
|--|---------|---------|
| "Golden dataset: 25 cases" | 错误 | 主测试集 25 条 |
| 人工 Golden Dataset | 未单独标注 | **9 条**（T04,T08,T11,T14,T17,T18,T21,T23,T25） |
| Reliability Stress Dataset | 未提及 | **32 条** |

## 修正前后对比

### PROMPT_AB_FULL_RESULT.md 需修正

1. 将 "V2 wins: 18/25 | Tie: 5/25 | V1 wins: 1/25" 修正为 "V2 wins: 19/25 | Tie: 5/25 | V1 wins: 1/25"

### PROMPT_AB_EXPERIMENT_REPORT.md 需修正

1. Section 7 将 T24 描述从 "prompt injection test case" 修正为 "空内容测试"
2. Section 2 将 "Golden dataset: 25 cases" 修正为 "主测试集: 25 cases, 人工 Golden Dataset: 9 cases"
3. Section 7 per-case table 补齐 T13 为 V2 胜

## 最终可信数据

| 指标 | 最终确认值 |
|------|-----------|
| 主测试集 | 25 条 |
| 人工 Golden Dataset | 9 条 |
| Stress Dataset | 32 条 |
| 总 API 调用 | 186 次 |
| V2 胜出 Case | **19/25** |
| V1 胜出 Case | 1/25 |
| 平局 Case | 5/25 |
| 失败运行 | 3 次（V1 T13） |
| V1 Avg Precision | 0.5063 |
| V2 Avg Precision | 0.6287 |
| Precision Lift | 1.24x (+24.2%) |
| V1 Avg Recall | 0.9906 |
| V2 Avg Recall | 0.9965 |
| V1 Success Rate | 96.00% |
| V2 Success Rate | 100.00% |
| V1 Avg Nodes | 20.0 |
| V2 Avg Nodes | 16.7 |
| V1 Node Range Pass | 40.74% |
| V2 Node Range Pass | 88.89% |
| V1 P95 Latency | 24,472ms |
| V2 P95 Latency | 20,400ms |
| Forbidden Violations | 0 (双方) |

---

*审计完成时间: 2026-08-04*
*审计方法: 从原始 JSON 独立重新计算所有指标，与报告逐项比对*
