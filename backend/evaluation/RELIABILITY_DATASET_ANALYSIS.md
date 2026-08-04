# Reliability Dataset Analysis

## 1. 当前 human_labels 数量

- 总样本数: **79**
- 已标注: 79/79 (100%)
- Placeholder: 0

## 2. 当前 label 分布

| Label | 数量 | 占比 |
|-------|------|------|
| correct | 79 | 100% |
| incorrect | 0 | 0% |
| missing | 0 | 0% |

## 3. 为什么无法有效计算 Cohen's Kappa / Evaluator P/R

### Cohen's Kappa

Kappa = (Po - Pe) / (1 - Pe)

当所有人工标签均为 "correct" 时:
- Human marginal: P(correct) = 79/79 = 1.0
- Evaluator marginal: P(correct) = 78/79 ≈ 0.987
- Pe (chance agreement) ≈ 0.987 (极高)
- Po (observed agreement) = 78/79 ≈ 0.987

当 Po ≈ Pe 时, Kappa ≈ 0 — 即使实际一致率很高。

**根因:** 单类别标签使得随机一致概率(Pe)与观察一致率(Po)几乎相等 — prevalence paradox。Kappa 需要多类别标签变异才能产生有意义的值。

### Evaluator Precision

定义: TP / (TP + FP)

- TP: evaluator 判 error 且 human 也判 error → 0 (无 human error labels)
- FP: evaluator 判 error 但 human 判 correct → 1 (T14 "12.8亿")
- Precision = 0 / (0 + 1) = 0.0

**根因:** 人工标签中无 incorrect/missing, TP 为 0, Precision 无法反映真实能力。

### Evaluator Recall

定义: TP / (TP + FN)

- TP: 0
- FN: human 判 error 但 evaluator 判 correct → 0 (无 human error labels)
- Recall = 0 / (0 + 0) = undefined (代码中输出 0.0)

**根因:** 人工标签无任何 error 案例, 分母为 0, Recall 无法定义。

## 4. 解决方案

创建 Reliability Stress Dataset:
- 人为构造包含 correct / incorrect / missing 三类标签的测试样本
- 基于真实 Golden Dataset 和 Agent 输出构造
- 验证 Evaluator 匹配层对三种情况的判断能力
- 实现有意义的 Kappa、Precision、Recall 计算

## 5. 当前 Evaluator Labels 结构

evaluator_labels.json (177 entries):
- correct: 78 — 匹配到 golden required_nodes 的 Agent 节点
- incorrect: 98 — Agent 生成但不在 required_nodes 中的节点 (false positives)
- missing: 1 — golden required_node 未被 Agent 生成 (T14 "12.8亿")
