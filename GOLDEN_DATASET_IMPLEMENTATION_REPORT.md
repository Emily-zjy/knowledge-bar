# Golden Dataset Integration — Implementation Report

## 概述

将人工标注的 Golden Dataset (9 cases) 集成到 Evaluation Runner 中，使评分系统能够基于专家标注的 required_nodes 计算 Precision/Recall，同时增加根节点验证、禁止节点检查、节点范围和深度验证。

## 修改文件

| 文件 | 操作 | 修改内容 |
|------|------|----------|
| `backend/evaluation/golden_dataset.json` | 新增 | 9 条人工标注数据 |
| `backend/evaluation/run_eval.py` | 修改 | 集成 golden dataset 评分逻辑 |

## Golden Dataset 结构

```json
{
  "case_id": "T04",
  "root": "Q3产品迭代规划",
  "required_nodes": ["决议事项", "待确认", ...],
  "optional_nodes": ["支付系统超时Bug", ...],
  "forbidden_nodes": ["虚构需求", ...],
  "expected_depth": 3,
  "node_range": [8, 18],
  "pass_criteria": "..."
}
```

**覆盖 Case:** T04, T08, T11, T14, T17, T18, T21, T23, T25

**特殊处理:** T14 的 `root` 为数组，表示多个可接受的根节点文本。

## Evaluator 修改说明

### 新增字段 (EvalResult)

| 字段 | 类型 | 说明 |
|------|------|------|
| `golden_annotated` | bool | 该 case 是否有 golden 标注 |
| `root_correct` | bool \| None | 根节点是否匹配 golden root |
| `forbidden_found` | list[str] | 生成结果中出现的禁止节点 |
| `depth_ok` | bool \| None | 深度是否满足 golden expected_depth |
| `node_count_ok` | bool \| None | 节点数是否在 golden node_range 内 |

### 评分逻辑变化

```
run_single_case(case):
    ...
    if case_id in GOLDEN_DATASET:
        # 使用 golden.required_nodes 替代 case.expected_nodes 计算 P/R
        # 增加 root 验证 (支持 string 和 array 两种格式)
        # 增加 forbidden_nodes 检查 (fuzzy substring match)
        # 增加 node_range 和 expected_depth 检查
    else:
        # 保持原有逻辑: 使用 case.expected_nodes + expected_structure
```

### 兼容性

- 非 golden case 的评分逻辑完全不变
- Precision/Recall 计算函数 `_compute_precision_recall` 未修改
- 模糊匹配规则 `_normalize` 未修改
- 不影响 Agent、Prompt、LLM Client 或 Schema Repair

## 验证结果

### 运行命令

```bash
python -m evaluation.run_eval --cases T04,T08,T11,T14,T17,T18,T21,T23,T25
```

### Golden Dataset 维度评估

| Case | Root | Forbidden | Range | Depth | P | R |
|------|------|-----------|-------|-------|------|------|
| T04 | ✓ | ✓ | ✗ | ✓ | 0.23 | 0.50 |
| T08 | ✓ | ✓ | ✓ | ✓ | 0.50 | 0.92 |
| T11 | ✓ | ✓ | ✗ | ✓ | 0.35 | 0.88 |
| T14 | ✓ | ✓ | ✗ | ✓ | 0.38 | 0.90 |
| T17 | ✓ | ✓ | ✗ | ✓ | 0.40 | 1.00 |
| T18 | ✓ | ✓ | ✓ | ✓ | 0.47 | 1.00 |
| T21 | ✓ | ✓ | ✓ | ✗ | 0.38 | 0.90 |
| T23 | ✓ | ✓ | ✗ | ✓ | 0.33 | 1.00 |
| T25 | ✓ | ✓ | ✓ | ✓ | 0.67 | 1.00 |

### 汇总

| 指标 | 结果 |
|------|------|
| 成功率 | 9/9 (100%) |
| Root correct | 9/9 (100%) |
| No forbidden | 9/9 (100%) |
| Node range OK | 4/9 (44%) |
| Depth OK | 8/9 (89%) |
| Golden Avg Precision | 0.4109 |
| Golden Avg Recall | 0.8998 |

### 分析

1. **Root 验证 100%** — 模型始终正确识别中心主题
2. **Forbidden 0 违规** — 模型没有产生幻觉内容或被 prompt injection 污染
3. **Node range 仅 44%** — 模型倾向生成较多节点 (通常超出 golden 标注的上限)。这是模型行为特征，非 bug
4. **Depth 89%** — 仅 T21 (超长文本) 未达到期望深度 4，生成深度为 3。长文本场景下模型倾向扁平化结构
5. **Recall 0.90** — golden required_nodes 提供了更精确的预期节点列表，大幅改善了评分的可解释性
6. **Precision 0.41** — 低于 Recall，因为模型生成的非根节点中只有约 41% 命中 required_nodes。考虑到 optional_nodes 未计入 precision，实际有效输出比例更高

### V1 Baseline 对比 (相同 9 case)

| 指标 | V1 (旧 expected_nodes) | Golden (required_nodes) |
|------|------------------------|-------------------------|
| Avg Precision | ~0.40 | 0.41 |
| Avg Recall | ~0.83 | 0.90 |
| 可解释性 | 低 (expected_nodes 为粗略估计) | 高 (人工验证的必选节点) |

Golden required_nodes 比原始 expected_nodes 更精确地反映了"正确输出应该包含什么"，Recall 提升约 7% 说明原来的 expected_nodes 列表偏松散。

## 未修改内容

- ✅ 测试输入 (test_cases.json) — 未修改
- ✅ 人工标注内容 (golden_dataset.json) — 忠实录入
- ✅ 模型调用逻辑 — 未修改
- ✅ Agent (ai_mindmap.py) — 未修改
- ✅ LLM Client — 未修改
- ✅ Schema Repair — 未修改
- ✅ Precision/Recall 算法 — 未修改

## 后续建议

1. **扩展 Golden Dataset** — 将其余 16 case 也进行人工标注，覆盖全部 25 case
2. **Optional nodes 纳入评分** — 当前 optional_nodes 仅作参考，可考虑给命中 optional 的节点加分
3. **Node range 调优** — 模型普遍生成较多节点，可考虑放宽标注范围上限或在 prompt 中加强节点数约束
4. **Composite Score 集成** — 将 golden 维度 (root_correct, no_forbidden) 加入综合评分计算
