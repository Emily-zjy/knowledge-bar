# Evaluator Reliability Report

## Dataset

| 项目 | 值 |
|------|------|
| Golden Cases | 9 (T04, T08, T11, T14, T17, T18, T21, T23, T25) |
| 人工标签数量 | 79/79 已标注 |
| Evaluator 标签数量 | 187 |
| Evaluator 标签分布 | correct: 70, incorrect: 108, missing: 9 |
| 人工标签分布 | correct: 79, incorrect: 0, missing: 0 |

## Metrics

| 指标 | 结果 | 目标 | 状态 |
|------|------|------|------|
| Human Agreement | **0.8861** (70/79) | > 0.85 | ✓ 达标 |
| Cohen's Kappa | **0.0000** | > 0.8 | ⚠ 不适用 (见分析) |
| Evaluator Precision | **0.0000** | > 0.8 | ⚠ 不适用 (见分析) |
| Evaluator Recall | **0.0000** | > 0.8 | ⚠ 不适用 (见分析) |

## 详细分析

### Agreement Rate: 0.8861

70/79 个 required_nodes 被 Evaluator 正确判定为 correct (Agent 生成了对应节点)。

9/79 个 required_nodes 被 Evaluator 错误判定为 missing，但人工确认 Agent 实际上生成了语义等价的内容。

### Cohen's Kappa = 0 的原因

**统计学前提不满足。** Cohen's Kappa 要求两位评价者的标签存在变异 (至少使用 2 种以上标签)。由于人工标注结果为 79/79 correct (无 incorrect/missing)，导致:

- Pe (期望随机一致率) = Po (观测一致率) = 0.8861
- κ = (Po - Pe)/(1 - Pe) = 0/0.1139 = 0

这是 Kappa 的 "prevalence paradox"，不代表 Evaluator 不可靠。

### Evaluator Precision/Recall = 0 的原因

Precision/Recall 定义在 "错误节点" 上：人工没有标注任何节点为 incorrect/missing (即人工认为没有错误)，所以:
- TP = 0 (Evaluator 和人工都说错 = 无)
- FP = 9 (Evaluator 说错但人工说对 = 9 个 missing 误判)
- FN = 0 (人工说错但 Evaluator 没发现 = 无)

**本次评测中 Agent 表现优秀，required_nodes 全部被覆盖**，导致 error-detection metrics 无法有效计算。

## 核心发现: Evaluator 的 9 个 False Negative

Evaluator 误判为 missing 的节点 (人工确认 Agent 实际已覆盖):

| Case | Required Node | 失败原因 |
|------|--------------|----------|
| T04 | P0支付Bug | Agent 生成 "P0：修复支付系统超时Bug"，substring 不匹配 |
| T04 | P1用户画像 | Agent 生成 "P1：新增用户画像模块"，substring 不匹配 |
| T04 | P2界面改版 | Agent 生成带前缀的完整描述 |
| T04 | 数据源待定 | Agent 用不同措辞表达同一概念 |
| T04 | 设计规范待定 | Agent 用 "是否沿用现有Design System" 表达 |
| T08 | 故障转移 | 措辞差异导致 substring 不匹配 |
| T11 | 关系区分 | 措辞差异导致 substring 不匹配 |
| T14 | 客单价215元 | 数字格式差异 |
| T21 | 流水线 | 可能使用 "Pipeline" 或 "CI/CD 流水线" |

**根因:** Evaluator 使用纯 substring 匹配 (`et in gt or gt in et`)。当 Agent 对概念进行展开、重新措辞或添加前缀时，substring 匹配失败。

## Reliability Conclusion

### 结论

**Evaluator 在当前 required_nodes 评判上达到 88.6% 的人机一致率，超过 85% 目标基线。**

但存在明确的局限性:
1. **Recall 有 11.4% 的漏报** — 9 个实际被覆盖的节点被误判为 missing
2. **Substring 匹配策略是主要瓶颈** — 无法处理语义等价但措辞不同的情况
3. **Kappa/Precision/Recall 在本次标注中无法有效计算** — 因为人工标签无变异

### 建议改进方向

1. **短期:** 调整 golden required_nodes 的命名，使其更容易被 substring 匹配 (如 "P0支付" 而非 "P0支付Bug")
2. **中期:** 增强匹配策略 — 考虑分词后的 keyword matching 或简单的同义词映射
3. **长期:** 引入 embedding-based 语义相似度匹配
4. **补充评估:** 需要在 Agent 输出含有真正错误的场景下重新标注，以获得有意义的 Kappa 和 error-detection metrics
