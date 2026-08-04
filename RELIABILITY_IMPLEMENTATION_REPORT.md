# Evaluator Reliability — Implementation Report

## 1. 新增文件

| 文件 | 用途 |
|------|------|
| `backend/evaluation/reliability/__init__.py` | 模块初始化 |
| `backend/evaluation/reliability/human_labels.json` | 人工标注模板 (79 条, PLACEHOLDER) |
| `backend/evaluation/reliability/evaluator_labels.json` | Evaluator 自动判断结果 (187 条) |
| `backend/evaluation/reliability/generate_evaluator_labels.py` | 从评测结果提取 evaluator labels |
| `backend/evaluation/reliability/reliability_metrics.py` | 可靠性指标计算 (Agreement, Kappa, P/R) |
| `backend/evaluation/reliability/README.md` | 模块使用说明 |
| `EVALUATOR_CURRENT_ANALYSIS.md` | Evaluator 现状分析 |
| `EVALUATOR_RELIABILITY_REPORT.md` | Reliability 评估报告 |

## 2. 修改文件

无。本模块不修改任何已有代码。

## 3. Reliability 架构

```
评测结果 (results/eval_*.json)
    │
    ▼
generate_evaluator_labels.py ──────► evaluator_labels.json
                                         │
                                         │  比对
                                         ▼
human_labels.json ──────────────────► reliability_metrics.py
 (人工填写)                              │
                                         ▼
                                    Reliability Report
                                    - Agreement Rate
                                    - Cohen's Kappa
                                    - Evaluator Precision
                                    - Evaluator Recall
```

### 数据流

1. `run_eval.py` 运行评测 → 生成 `results/eval_*.json`
2. `generate_evaluator_labels.py` 提取 per-node 判断 → `evaluator_labels.json`
3. 人工标注员填写 `human_labels.json` (独立于系统, 不可自动化)
4. `reliability_metrics.py` 比对两份标签 → 输出可靠性指标

### 隔离原则

- Evaluator 的判断来自实际运行结果, 不可手动编造
- Human labels 来自人工判断, 不可用 LLM 生成
- Reliability 模块只读取数据, 不修改 Agent 或 Evaluator

## 4. human_labels 设计原则

### 标签体系

| 标签 | 定义 | 对应 Evaluator 行为 |
|------|------|-------------------|
| `correct` | Agent 生成节点正确命中 required_node | Evaluator 将其匹配到 expected |
| `incorrect` | Agent 生成节点错误/幻觉/无关 | Evaluator 列为 false_positive |
| `missing` | Golden required_node 未被生成 | Evaluator 列为 missed_nodes |

### 模板结构

```json
{
  "case_id": "T04",
  "node": "P1用户画像",
  "human_label": "PLACEHOLDER",
  "comment": "待人工标注"
}
```

### 标注范围

- 覆盖全部 9 个 golden case 的 required_nodes (79 条)
- 每条 required_node 都需要人工判断: Agent 是否正确覆盖了它
- 判断依据: 查看 Agent 生成节点列表, 对照 golden 标准

### 安全措施

- 全部初始化为 PLACEHOLDER
- 脚本检测到全部 PLACEHOLDER 时输出等待提示, 不生成虚假结果
- 无法绕过人工标注步骤

## 5. 指标计算方式

### Human Agreement Rate

```
agreement_rate = 一致判断数 / 总比对数
```

将 human_label 和 evaluator_label 按 (case_id, node) 配对, 统计完全一致的比例。

### Cohen's Kappa

```
κ = (Po - Pe) / (1 - Pe)

Po = 观测一致率 (实际一致的比例)
Pe = 期望一致率 (两位评价者随机情况下的一致概率)
```

计算方式:
1. 构建 3×3 混淆矩阵 (correct/incorrect/missing × correct/incorrect/missing)
2. Po = 对角线之和 / 总数
3. Pe = Σ(human_marginal_i × evaluator_marginal_i)
4. κ = (Po - Pe) / (1 - Pe)

解读:
- κ > 0.8: 优秀 (highly reliable)
- 0.6 < κ ≤ 0.8: 可接受 (acceptable)
- κ ≤ 0.6: 需要优化 (needs improvement)

### Evaluator Precision

```
Evaluator_Precision = TP / (TP + FP)

TP: Evaluator 判错 & 人工也判错
FP: Evaluator 判错 & 但人工判正确
```

含义: Evaluator 报告的"错误"中, 有多大比例是真正的错误。

### Evaluator Recall

```
Evaluator_Recall = TP / (TP + FN)

TP: Evaluator 判错 & 人工也判错
FN: Evaluator 判正确 & 但人工判错
```

含义: 真正的错误中, Evaluator 发现了多大比例。

## 6. 如何进行人工校准

### 步骤

1. **准备环境**
   ```bash
   cd backend
   python -m evaluation.run_eval --cases T04,T08,T11,T14,T17,T18,T21,T23,T25
   python -m evaluation.reliability.generate_evaluator_labels
   ```

2. **标注准备**
   - 打开 `evaluation/results/` 最新结果文件
   - 打开 `evaluation/golden_dataset.json`
   - 打开 `evaluation/reliability/human_labels.json`

3. **逐条标注**
   - 对每个 `(case_id, node)` 对:
     - 在评测结果中找到该 case 的 `generated_nodes`
     - 判断: 该 required_node 是否被正确覆盖?
     - 如果生成节点中有等价文本 → `correct`
     - 如果生成节点中完全没有对应内容 → `missing`
     - 如果这是一个额外的 incorrect 判断 → `incorrect`

4. **运行验证**
   ```bash
   python -m evaluation.reliability.reliability_metrics
   ```

5. **解读结果**
   - Kappa > 0.8: Evaluator 可靠, 可信赖其自动评分
   - Kappa < 0.6: Evaluator 需优化 (可能 fuzzy matching 策略需调整)

### 校准频率

- 首次: 完成全部 79 条标注
- 后续: 每次修改 Evaluator 匹配逻辑后重新校准
- 扩展: 新增 golden case 时补充对应 human_labels

## 7. 后续使用流程

```
┌─────────────────────────────────────────────────┐
│ 日常流程                                         │
│                                                  │
│ 1. 修改 Evaluator 匹配逻辑                       │
│    ↓                                             │
│ 2. 运行评测                                      │
│    python -m evaluation.run_eval                 │
│    ↓                                             │
│ 3. 重新生成 evaluator_labels                     │
│    python -m evaluation.reliability              │
│           .generate_evaluator_labels             │
│    ↓                                             │
│ 4. 运行 reliability check                       │
│    python -m evaluation.reliability              │
│           .reliability_metrics                   │
│    ↓                                             │
│ 5. 确认 Kappa 未下降                             │
│    ↓                                             │
│ 6. 如果 Kappa 下降 → 检查修改是否引入问题         │
│                                                  │
└─────────────────────────────────────────────────┘
```

### 扩展路径

| 阶段 | 工作 |
|------|------|
| 当前 | 完成 79 条人工标注, 建立 baseline |
| 短期 | 根据 Reliability 结果调优 Evaluator 匹配策略 |
| 中期 | 扩展 golden dataset 到 25 cases, 补充 human_labels |
| 长期 | 引入 Inter-Annotator Agreement (多人标注一致性) |

## 验证方式

```bash
# 1. 模块语法检查
python -c "import ast; ast.parse(open('evaluation/reliability/reliability_metrics.py').read()); print('OK')"

# 2. 运行 reliability (应显示 Waiting for human annotation)
python -m evaluation.reliability.reliability_metrics

# 3. 生成 evaluator labels
python -m evaluation.reliability.generate_evaluator_labels

# 4. 验证 evaluator_labels.json 非空
python -c "import json; d=json.load(open('evaluation/reliability/evaluator_labels.json')); print(f'{len(d)} labels')"
```
