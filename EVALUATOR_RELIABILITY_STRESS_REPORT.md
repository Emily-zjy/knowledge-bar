# Evaluator Reliability Stress Report

## Dataset

| 项目 | 值 |
|------|------|
| 样本数量 | 32 |
| 来源 | Golden Dataset (T04, T08, T11, T14, T17, T18, T21, T23, T25) |
| 构造方式 | 基于真实Agent输出 + 人工构造错误/缺失场景 |

### Label 分布

| Label | 数量 | 占比 |
|-------|------|------|
| correct | 13 | 40.6% |
| incorrect | 10 | 31.3% |
| missing | 9 | 28.1% |

## Metrics

### Human Agreement

| 指标 | 值 |
|------|------|
| Agreement Rate | **0.7812** (25/32) |
| Disagreements | 7 |

### Cohen's Kappa

| 指标 | 值 |
|------|------|
| Kappa | **0.6570** |
| Po (observed) | 0.7812 |
| Pe (chance) | 0.3623 |
| Interpretation | Acceptable (0.6-0.8) |

### Evaluator Precision / Recall

| 指标 | 值 | 说明 |
|------|------|------|
| Precision | **1.0000** | 当Evaluator判定为错误时，100%准确 |
| Recall | **0.6316** | 19个真实错误中识别了12个 |
| TP | 12 | 正确识别的错误 |
| FP | 0 | 无误判 |
| FN | 7 | 漏判的错误 |

### Confusion Matrix

| Human \ Evaluator | correct | incorrect | missing |
|-------------------|---------|-----------|---------|
| correct | **13** | 0 | 0 |
| incorrect | 7 | **3** | 0 |
| missing | 0 | 0 | **9** |

## Disagreement Analysis

所有 7 个分歧均为：human=incorrect 但 evaluator=correct

| # | Case | Golden Node | Agent Output | 错误类型 | 匹配原因 |
|---|------|-------------|--------------|----------|----------|
| 1 | stress_014 | Redis Cluster | MongoDB Cluster | 技术方案错误 | "Cluster" 关键词匹配 |
| 2 | stress_015 | 缓存雪崩 | 缓存策略优化 | 概念泛化 | "缓存" 关键词匹配 |
| 3 | stress_016 | Hash Slot | 一致性Hash | 技术概念错误 | "Hash" 关键词匹配 |
| 4 | stress_018 | 12.8亿 | 15.2亿 | 数据错误 | "亿" 字符匹配 |
| 5 | stress_020 | 快速排序 | GPU并行排序 | 幻觉内容 | "排序" 关键词匹配 |
| 6 | stress_021 | B+树索引 | 红黑树索引 | 技术概念错误 | "索引" 关键词匹配 |
| 7 | stress_023 | 测试金字塔 | 自动化测试框架 | 概念不等价 | "测试" 关键词匹配 |

### 根因分析

当前 Evaluator 匹配层设计目标是**概念覆盖验证**（节点是否存在），而非**事实正确性验证**（节点内容是否准确）。

匹配层的局限:
1. **关键词重叠导致误匹配** — "Redis Cluster" vs "MongoDB Cluster" 共享 "Cluster"
2. **无法验证数值** — "12.8亿" vs "15.2亿" 共享 "亿"
3. **无法区分同类不同实体** — "B+树" vs "红黑树" 共享 "索引"
4. **无法判断泛化/具体化关系的正确性** — "缓存雪崩" vs "缓存策略优化" 共享 "缓存"

这些错误需要**事实验证层**（Fact-Checking Layer），超出文本匹配的能力范围。

## Reliability Conclusion

| 维度 | 评价 |
|------|------|
| 概念覆盖检测 (correct + missing) | **优秀** — 22/22 完全正确 |
| 事实错误检测 (incorrect) | **不足** — 仅 3/10 正确识别 |
| 总体 Kappa | **0.6570 — Acceptable** |

**结论: ACCEPTABLE — Evaluator 在概念覆盖检测方面高度可靠，但缺乏事实正确性验证能力。**

当前 Evaluator 适用于:
- 验证 Agent 是否生成了必要概念节点 (correct/missing 判断)
- 不适用于验证 Agent 生成内容的事实准确性 (incorrect 判断)

## 后续优化方向

1. **Fact-Checking Layer** — 增加数值精确匹配（数字+单位必须完全一致）
2. **Entity Disambiguation** — "Redis" vs "MongoDB" 应视为不同实体，即使都是数据库
3. **Strict Mode** — 对数据报告类 case (T14) 启用严格数值匹配
4. **Embedding-based 语义验证** — 使用 EmbeddingSemanticMatcher 增强区分能力
