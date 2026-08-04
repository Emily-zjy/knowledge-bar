# Evaluator Matching Analysis

## 当前匹配方式

### 1. required_nodes 匹配 (Precision/Recall)

**位置:** `run_eval.py:124-153` — `_compute_precision_recall()`

**流程:**
```
1. 提取生成节点文本 (排除根节点) → gen_texts
2. 提取期望节点文本 → exp_texts
3. 两者都经过 _normalize() 处理:
   - lowercase
   - strip
   - 移除所有空格
   - 全角括号→半角
4. 遍历 gen_texts × exp_texts:
   - if et in gt or gt in et → matched
   - 每个 exp 只能匹配一次 (greedy, first-match)
```

**匹配策略:** 纯 substring 包含关系。

### 2. forbidden_nodes 匹配

**位置:** `run_eval.py:264-272`

**流程:** 同样使用 `_normalize()` + substring (`fb_norm in gt or gt in fb_norm`)

### 3. root 匹配

**位置:** `run_eval.py:250-257`

**流程:** 同样使用 `_normalize()` + substring

## 导致 False Negative 的具体位置

**核心问题在 `_compute_precision_recall()` 第 141 行:**

```python
if et in gt or gt in et:
```

当 golden required_node 经过 normalize 后为 `"p0支付bug"`，而 Agent 生成的节点 normalize 后为 `"p0：修复支付系统超时bug"` 时：

- `"p0支付bug" in "p0：修复支付系统超时bug"` → **False** (因为 "支付" 和 "bug" 之间插入了其他字符)
- `"p0：修复支付系统超时bug" in "p0支付bug"` → **False**

结果：未匹配，该 required_node 被判为 missing。

## 9 个 False Negative 详细分析

| # | Case | Required Node | Normalized | Agent Generated | Normalized | 失败原因 |
|---|------|--------------|-----------|-----------------|------------|---------|
| 1 | T04 | P0支付Bug | p0支付bug | P0：修复支付系统超时Bug | p0：修复支付系统超时bug | "支付bug" 被 "修复支付系统超时bug" 中间内容打断 |
| 2 | T04 | P1用户画像 | p1用户画像 | P1：新增用户画像模块 | p1：新增用户画像模块 | "p1用户画像" 不是子串 |
| 3 | T04 | P2界面改版 | p2界面改版 | P2：界面改版 | p2：界面改版 | "p2界面改版" vs "p2：界面改版" — 冒号阻断 |
| 4 | T04 | 数据源待定 | 数据源待定 | 用户画像数据源：埋点 vs 问卷 | 用户画像数据源：埋点vs问卷 | 完全不同措辞 |
| 5 | T04 | 设计规范待定 | 设计规范待定 | 是否沿用现有Design System | 是否沿用现有designsystem | 完全不同措辞 |
| 6 | T08 | 故障转移 | 故障转移 | (需检查具体输出) | — | 可能加了前缀或描述 |
| 7 | T11 | 关系区分 | 关系区分 | (需检查具体输出) | — | 可能措辞变化 |
| 8 | T14 | 客单价215元 | 客单价215元 | (需检查具体输出) | — | 可能数字格式不同 |
| 9 | T21 | 流水线 | 流水线 | (需检查具体输出) | — | 可能使用 "CI/CD流水线" 或 "Pipeline" |

## 匹配策略局限性总结

| 局限 | 影响 | 示例 |
|------|------|------|
| 无法跨越插入字符 | required_node 的关键词被其他内容隔开时失败 | "支付Bug" vs "修复支付系统超时Bug" |
| 无法忽略标点 | 冒号、句号等阻断子串 | "P2界面改版" vs "P2：界面改版" |
| 无法处理语义等价 | 同一概念用不同词表达 | "数据源待定" vs "数据源：埋点vs问卷" |
| 无法处理缩写/展开 | 缩略语与完整表达不匹配 | "流水线" vs "CI/CD Pipeline" |

## 改进方向

1. **Layer 1 (Exact):** 保持当前 normalize + 完全相等
2. **Layer 2 (Keyword):** 去除标点后提取关键词，多数关键词命中即匹配
3. **Layer 3 (Semantic):** 预留语义相似度接口，用于无法通过关键词匹配的情况
