# Evaluator Current Analysis

## 概述

本文档分析 `backend/evaluation/run_eval.py` 中自动评估器 (Evaluator) 的当前逻辑，为 Evaluator Reliability 验证提供基础。

## Evaluator 判断流程

### 输入

1. **测试用例** (`test_cases.json`) — 包含 `input_text`, `expected_nodes`, `expected_structure`
2. **Golden Dataset** (`golden_dataset.json`) — 对 9 个标注 case 提供 `required_nodes`, `optional_nodes`, `forbidden_nodes`, `root`, `expected_depth`, `node_range`
3. **Agent 生成结果** — 调用 `generate_mind_map()` 后返回的 `MindMapData` (nodes 列表)

### 判断逻辑

#### 1. 节点匹配 (Precision/Recall)

核心函数: `_compute_precision_recall(generated_nodes, expected_nodes)`

```
匹配规则:
  1. 将生成节点 text 和期望节点 text 都经过 _normalize() 处理
     - _normalize: lowercase + strip + 移除空格 + 统一括号
  2. 对每个生成节点 gt, 遍历期望节点 et:
     - 如果 et in gt 或 gt in et → 判定为匹配 (fuzzy substring)
  3. 统计:
     - matched_gen: 匹配上的生成节点
     - matched_exp: 匹配上的期望节点
     - precision = matched / total_generated (非根)
     - recall = matched / total_expected
```

**Evaluator 对每个节点的隐含判断:**

| 情况 | Evaluator 隐含标签 |
|------|-------------------|
| 生成节点匹配上 required_node | `correct` |
| 生成节点未匹配任何 required_node | `incorrect` (false positive) |
| required_node 未被任何生成节点匹配 | `missing` |

#### 2. 根节点验证 (仅 Golden case)

```
- 对 golden.root (string 或 array) 与 generated_root 做 fuzzy substring 匹配
- 输出: root_correct (bool)
```

#### 3. 禁止节点检查 (仅 Golden case)

```
- 对所有生成节点的 text 与 golden.forbidden_nodes 做 fuzzy substring 匹配
- 任何匹配即视为禁止节点出现
- 输出: forbidden_found (list[str])
```

#### 4. 结构验证

```
- node_range: node_count 是否在 [min, max] 之间
- expected_depth: 实际深度是否 >= expected_depth - 1
```

### 输出格式

```json
{
  "case_id": "T04",
  "success": true,
  "generated_nodes": [...],
  "generated_root": "Q3产品迭代规划",
  "node_count": 23,
  "depth": 3,
  "precision": 0.2273,
  "recall": 0.5,
  "false_positives": ["参会人", "产品负责人张三", ...],
  "missed_nodes": ["P0支付Bug", "P1用户画像", ...],
  "golden_annotated": true,
  "root_correct": true,
  "forbidden_found": [],
  "depth_ok": true,
  "node_count_ok": false
}
```

## 可比较字段 (用于 Reliability 验证)

Evaluator 产生的每个 per-node 判断可以转换为标准标签:

| Evaluator 输出 | 对应标签 | 说明 |
|---------------|----------|------|
| 节点出现在 `matched_gen` 中 | `correct` | 生成节点命中了 required_node |
| 节点出现在 `false_positives` 中 | `incorrect` | 生成节点未命中任何 required_node |
| 节点出现在 `missed_nodes` 中 | `missing` | required_node 未被生成 |
| 节点出现在 `forbidden_found` 中 | `incorrect` | 禁止内容被生成 |

### 转换方式

从 evaluation results JSON 中, 对每个 golden case:

1. **correct 节点**: `generated_nodes` 中 text 不在 `false_positives` 中的非根节点
2. **incorrect 节点**: `false_positives` 列表中的所有节点
3. **missing 节点**: `missed_nodes` 列表中的所有节点

## Evaluator 局限性

1. **Fuzzy matching 可能过度匹配** — `et in gt or gt in et` 可能将部分匹配误判为正确
2. **Fuzzy matching 可能遗漏** — 语义相同但措辞不同的节点不会匹配 (如 "P0支付Bug" vs "P0：修复支付系统超时Bug")
3. **不区分 optional 和 required** — precision 计算中，命中 optional_node 的节点被视为 false positive
4. **结构关系未验证** — 只验证节点文本存在，不验证父子层级是否正确

## 结论

Evaluator 的核心判断机制是基于 substring 的模糊文本匹配。这种方法简单高效但存在误判风险，特别是:
- 较短的 required_node 名称可能错误匹配到不相关的长节点
- 语义等价但措辞不同的内容无法识别

这正是需要 Evaluator Reliability 验证的原因: 通过人工标注对比，量化自动评估器与人类判断的一致性。
