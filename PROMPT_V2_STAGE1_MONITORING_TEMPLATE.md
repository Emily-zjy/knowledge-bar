# Prompt V2 — Stage 1 Monitoring Template

## 监控周期

- 灰度比例: 10%
- 观察窗口: 至少 72 小时
- 检查频率: 每 24 小时一次
- **结束条件: 持续至少 72 小时 且 V2 真实请求数至少 50 条**

---

## 关键指标（所有指标按 prompt_version 分组）

### 1. 成功率（Success Rate）

| 指标 | V1 基线 | V2 目标 | 观察区间 | 回滚阈值 |
|------|---------|---------|----------|----------|
| 生成成功率 | 96-100% | >=97% | 95%-97% | <95% 或连续1小时<90% |
| Empty Response Rate | ~0% | <2% | 2%-5% | >5% |
| Retry Rate | <5% | <5% | 5%-10% | >10% |
| Schema Repair Rate | <10% | <10% | 10%-20% | >20% |

### 2. 延迟（Latency）

| 指标 | V1 基线 | 告警阈值 | 字段 |
|------|---------|----------|------|
| P50 延迟 | ~7s | > 12s | `total_latency_ms` |
| P95 延迟 | ~20s | > 30s | `total_latency_ms` |
| LLM P50 | ~6s | > 10s | `llm_latency_ms` |

### 3. 输出质量（Output Quality）

| 指标 | V1 基线 | V2 离线目标 | 告警阈值 | 判定方式 |
|------|---------|-------------|----------|----------|
| 平均节点数 | 20.0 | 16.7 | > 25 或 < 5 | `output_json.node_count` |
| 节点数范围合规 | **40.7%** | **88.9%** | < 70% | 6-25 nodes |
| Empty Response | 0% | 0% | > 5% | `output_json.node_count == 0` |

### 4. 安全指标

| 指标 | 预期值 | 告警阈值 | 判定方式 |
|------|--------|----------|----------|
| Prompt Injection 污染 | 0% | >0% | trace 输出含 script/hacked/指令执行痕迹 |
| HTML/script 异常输出 | 0% | >0% | node text 含 `<script>` / `<img` / `javascript:` |

### 5. Error Type 分布

| 错误类型 | 预期比例 | 告警阈值 |
|----------|----------|----------|
| AI_INVALID_JSON | <4% | >10% |
| AI_INVALID_SCHEMA | <2% | >5% |
| SCHEMA_REPAIR_FAILED | <2% | >5% |
| LLM_TIMEOUT | <3% | >8% |
| LLM_ERROR | <2% | >5% |
| 未知错误 | 0% | >0% |

### 6. 分流健康度（Rollout Health）

| 指标 | 预期值 | 异常阈值 | 字段 |
|------|--------|----------|------|
| V2 流量占比 | ~10% | < 5% 或 > 20% | `prompt_version=v2` 比例 |
| bucket 分布 | 均匀 0-9 | 严重偏斜 | `prompt_bucket` |
| key_type 分布 | 主要 knowledge_base_id | 大量 none | `prompt_assignment_key_type` |

### 7. 用户行为指标

| 指标 | 数据来源 | 当前状态 |
|------|----------|----------|
| 用户重新生成率 | regenerate API 调用频率 | NOT_INSTRUMENTED |
| 用户删除节点数 | patch/delete API 调用 | NOT_INSTRUMENTED |
| 用户编辑节点数 | patch API (update_node) | NOT_INSTRUMENTED |

> 以上用户行为指标当前无独立埋点，需后续迭代加入。Stage 1 期间标记为 NOT_INSTRUMENTED。

---

## 每日检查清单

### Day 1 (T+24h)

- [ ] V2 成功率 >= 97%（观察: 95-97%，回滚: <95%）
- [ ] V2 P95 延迟 <= 30s
- [ ] V2 流量比例 8-12%
- [ ] Empty Response Rate < 2%
- [ ] Retry Rate < 5%
- [ ] Schema Repair Rate < 10%
- [ ] 无 Injection 污染
- [ ] 无 HTML/script 异常
- [ ] Error Type 分布正常
- [ ] 节点数合理（均值 10-20）

### Day 2 (T+48h)

- [ ] 成功率趋势稳定（无下降）
- [ ] 延迟趋势稳定（无上升）
- [ ] 无用户反馈问题
- [ ] bucket 分布无异常偏斜
- [ ] V2 累计请求数进度（目标: 50 条）
- [ ] 节点范围合规率 >= 70%

### Day 3 (T+72h)

- [ ] V2 累计请求数 >= 50
- [ ] 综合评估：V2 表现 >= V1
- [ ] 节点范围合规率是否接近离线目标 88.9%
- [ ] 决策：维持 10% / 提升到 30% / 回滚到 0%

---

## 结束条件判定

Stage 1 结束需**同时满足**:

| 条件 | 阈值 | 当前 |
|------|------|------|
| 持续时间 | >= 72 小时 | — |
| V2 真实请求数 | >= 50 条 | — |

**不满足任一条件时，继续观察。不得提前声明 Stage 1 Complete。**

---

## 告警与回滚触发条件

### 立即回滚（设置 AI_PROMPT_V2_PERCENTAGE=0）

- V2 成功率连续 1 小时 < 90%
- V2 成功率单日 < 95%
- V2 P95 延迟连续 1 小时 > 40s
- Prompt Injection 污染 > 0 条
- HTML/script 异常输出 > 0 条
- 出现非预期错误码
- 用户投诉导图内容明显错误（数字篡改、编造内容）

### 观察但暂不回滚

- V2 成功率 95-97%
- V2 延迟比 V1 高 10-20%
- 节点数偏低但内容正确
- Retry Rate 5-10%

### 提升灰度条件（10% → 30%）

- 72 小时 + 50 条 V2 请求全部满足
- V2 成功率 >= 97%
- V2 P95 延迟 <= V1 P95 × 1.1
- 无 critical/major 问题
- 节点范围合规率 >= 80%
- Empty Response Rate < 2%
- 0 条安全异常
- 0 条用户投诉

---

## 回滚操作

```bash
# 立即回滚: 设置百分比为 0
# Railway 环境变量修改:
AI_PROMPT_V2_PERCENTAGE=0

# 重启/重新部署生效
# 回滚后所有请求使用 V1，trace 中 prompt_assignment_mode 仍为 stable_hash
# 但 prompt_rollout_percentage=0 表明已回滚
```

---

## 阶段推进计划

| 阶段 | 比例 | 最少观察期 | 最少 V2 请求 | 进入条件 |
|------|------|-----------|-------------|----------|
| Stage 1 | 10% | 72h | 50 条 | Stage 0 通过 |
| Stage 2 | 30% | 72h | 150 条 | Stage 1 全部指标达标 |
| Stage 3 | 50% | 48h | 250 条 | Stage 2 无回归 |
| Stage 4 | 100% | 持续 | — | Stage 3 稳定 |

---

*模板更新: 2026-08-04*
*适用期: Stage 1 (10% 灰度) 观察窗口*
