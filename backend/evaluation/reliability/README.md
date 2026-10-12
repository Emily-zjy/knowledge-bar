# Evaluator Reliability Module

## 目的

验证自动评估器 (Evaluator) 的判断是否接近真实人工判断。

评估对象是 **Evaluator**，不是 Agent。

## 文件结构

```
reliability/
├── __init__.py
├── human_labels.json          # 人工标注 (需手动填写)
├── evaluator_labels.json      # Evaluator 自动判断结果
├── generate_evaluator_labels.py  # 从评测结果提取 evaluator labels
├── reliability_metrics.py     # 可靠性指标计算
└── README.md                  # 本文件
```

## 使用流程

### 1. 运行评测 (已完成)

```bash
cd backend
python -m evaluation.run_eval --cases T04,T08,T11,T14,T17,T18,T21,T23,T25
```

### 2. 生成 evaluator_labels.json

```bash
python -m evaluation.reliability.generate_evaluator_labels
```

从最新的评测结果中提取 Evaluator 对每个节点的判断。

### 3. 人工填写 human_labels.json

打开 `human_labels.json`，将每条记录的 `human_label` 从 `"PLACEHOLDER"` 改为：

| 标签 | 含义 |
|------|------|
| `correct` | Agent 生成的节点命中了 golden required_node，内容正确 |
| `incorrect` | Agent 生成的节点是错误的、幻觉的、或无关的 |
| `missing` | Golden required_node 应该出现但 Agent 没有生成 |

判断依据：

- 查看 `evaluation/results/` 中对应 case 的 `generated_nodes`
- 对照 `golden_dataset.json` 中的 `required_nodes`
- 用人类判断力决定 Evaluator 的 fuzzy matching 是否正确

可选填写 `comment` 字段说明理由。

### 4. 运行可靠性检查

```bash
python -m evaluation.reliability.reliability_metrics
```

### 5. 解读结果

| 指标 | 说明 | 目标 |
|------|------|------|
| Agreement Rate | 人机一致率 | > 0.85 |
| Cohen's Kappa | 排除随机一致后的可靠性 | > 0.8 优秀, > 0.6 可接受 |
| Evaluator Precision | Evaluator 判为错误的节点中确实错误的比例 | > 0.8 |
| Evaluator Recall | 真正错误节点中 Evaluator 找到的比例 | > 0.8 |

## 注意事项

- human_labels.json 必须由人工填写，禁止使用 LLM 生成
- 如果 human_labels 全部为 PLACEHOLDER，脚本会提示等待人工标注
- evaluator_labels.json 必须从实际评测结果中生成，不可手动编造
- 每次重新运行评测后，应重新生成 evaluator_labels.json
