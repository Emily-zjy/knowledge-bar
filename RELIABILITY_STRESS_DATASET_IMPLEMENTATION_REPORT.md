# Reliability Stress Dataset Implementation Report

## 1. 新增文件

| 文件 | 说明 |
|------|------|
| `backend/evaluation/reliability/stress_dataset.json` | 32条压力测试样本 (correct/incorrect/missing) |
| `backend/evaluation/reliability/stress_human_labels.json` | 人工标注标签 (stress test 专用) |
| `backend/evaluation/reliability/stress_reliability_metrics.py` | 压力测试可靠性度量脚本 |
| `backend/evaluation/RELIABILITY_DATASET_ANALYSIS.md` | 当前数据分析报告 |

## 2. Stress Dataset 设计原则

### 样本来源

所有样本基于真实 Golden Dataset (T04-T25) 和真实 Agent 输出构造:
- **correct 样本**: 取自实际 Agent 成功匹配的节点对
- **incorrect 样本**: 将真实节点替换为同类但错误的内容 (如 Redis→MongoDB)
- **missing 样本**: 取自 Golden 中 Agent 可能遗漏的节点

### 分布设计

| 类别 | 数量 | 占比 | 设计目标 |
|------|------|------|----------|
| correct | 13 | 40.6% | 验证正常匹配不被破坏 |
| incorrect | 10 | 31.3% | 验证错误内容能否被识别 |
| missing | 9 | 28.1% | 验证缺失节点能否被检测 |

### 无类别不平衡

三类标签分布接近均匀 (40/30/30)，避免 prevalence paradox。

## 3. 错误类型覆盖

| 错误类型 | 示例 | 样本数 |
|----------|------|--------|
| 技术方案错误 | Redis Cluster → MongoDB Cluster | 2 |
| 数据错误 | 12.8亿 → 15.2亿 | 2 |
| 概念泛化 | 缓存雪崩 → 缓存策略优化 | 1 |
| 技术概念混淆 | Hash Slot → 一致性Hash | 1 |
| 幻觉内容 | 快速排序 → GPU并行排序 | 1 |
| 事实相反 | 未达成一致 → 已决定采用 | 1 |
| 概念不等价 | 测试金字塔 → 自动化测试框架 | 2 |

## 4. 人工标注规范

### 标注原则

1. **human_label 代表人工判断** — 非 LLM 自动生成
2. **每条标注附带 comment** — 解释判断依据
3. **三值标签**: correct / incorrect / missing
4. **基于语义等价性判断**, 非纯文本匹配

### 标注定义

| Label | 定义 | 判断标准 |
|-------|------|----------|
| correct | Agent 输出与 Golden 语义一致 | 完全一致 / 关键词等价 / 语义等价 |
| incorrect | Agent 输出与 Golden 语义不一致 | 错误数据 / 错误概念 / 幻觉 / 事实相反 |
| missing | Golden 要求但 Agent 未生成 | agent_output_node = null |

### 禁止行为

- 禁止 LLM 自动生成最终 human_labels
- 禁止 Evaluator 生成 human_labels
- 禁止根据 Evaluator 结果反推 human_labels

## 5. 指标计算方式

### Human Agreement

```
Agreement = matched_labels / total_paired_labels
```

### Cohen's Kappa

```
Kappa = (Po - Pe) / (1 - Pe)

Po = observed agreement (对角线之和 / 总数)
Pe = chance agreement (各类别边际概率乘积之和)
```

### Evaluator Precision (Error Detection)

```
Precision = TP / (TP + FP)

TP: evaluator 判 error 且 human 判 error
FP: evaluator 判 error 但 human 判 correct
```

### Evaluator Recall (Error Detection)

```
Recall = TP / (TP + FN)

TP: evaluator 判 error 且 human 判 error
FN: evaluator 判 correct 但 human 判 error
```

"Error" = incorrect 或 missing

## 6. 最终 Reliability 结果

| 指标 | 值 | 评价 |
|------|------|------|
| Human Agreement | 0.7812 (25/32) | — |
| Cohen's Kappa | **0.6570** | Acceptable (0.6-0.8) |
| Evaluator Precision | **1.0000** | 完美 — 无误判 |
| Evaluator Recall | **0.6316** | 中等 — 漏判 7/19 |
| correct 准确率 | 13/13 (100%) | 完美 |
| missing 准确率 | 9/9 (100%) | 完美 |
| incorrect 准确率 | 3/10 (30%) | 不足 |

### 关键发现

1. **概念覆盖维度 (correct + missing): 100% 准确** — Evaluator 在判断节点是否存在方面高度可靠
2. **事实正确性维度 (incorrect): 30% 准确** — 匹配层无法区分"文本相似但事实错误"的情况
3. **Precision = 1.0** — 当 Evaluator 报错时，一定是真的错了 (高可信度)
4. **Recall = 0.63** — 部分事实错误被漏判 (宽松匹配的代价)

## 7. 后续优化方向

### 短期 (提高 incorrect 识别率)

1. **数值精确匹配规则** — 对含数字的节点要求数值完全一致 (12.8亿 ≠ 15.2亿)
2. **实体消歧** — 同类词前缀不同时降低匹配分 (Redis ≠ MongoDB, B+树 ≠ 红黑树)
3. **严格模式开关** — 数据密集型 case 启用更严格的匹配阈值

### 中期 (架构层面)

4. **Fact-Checking Layer** — 在匹配层之上增加事实验证层
5. **EmbeddingSemanticMatcher** — 使用多语言 embedding 增强语义区分
6. **否定语义检测** — "未达成一致" vs "已决定采用" 应被识别为语义相反

### 长期 (数据层面)

7. **扩展 stress dataset** — 增加到 100+ 样本覆盖更多错误模式
8. **Multi-annotator agreement** — 多人标注消除个人偏差
9. **自适应阈值** — 基于 stress test 结果自动优化匹配阈值

## 验证方式

```bash
cd backend

# 运行压力测试 reliability
python -m evaluation.reliability.stress_reliability_metrics

# 预期输出:
#   Kappa: 0.6570
#   Precision: 1.0000
#   Recall: 0.6316
#   Conclusion: ACCEPTABLE
```
