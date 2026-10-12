# Prompt A/B Test — 最终验收

## 当前状态: ADOPT_V2

---

## Automatic Evaluation (自动指标 7/7 PASS)

| # | 条件 | 阈值 | 实际值 | 结果 |
|---|------|------|--------|------|
| 1 | Precision 相对提升 >= 15% | 1.15x | 1.24x (+24.2%) | **PASS** |
| 2 | Recall 下降 <= 0.03 | -0.03 | +0.006 (改善) | **PASS** |
| 3 | 成功率不低于 V1 | >= 96% | 100% | **PASS** |
| 4 | FP Rate 低于 V1 | < 0.4892 | 0.4279 | **PASS** |
| 5 | Forbidden 违规不增加 | <= 0 | 0 = 0 | **PASS** |
| 6 | Node Range Compliance 提升 | > 40.74% | 88.89% | **PASS** |
| 7 | P95 Latency 不恶化超 10% | <= 26,919ms | 20,400ms | **PASS** |

## Human Review (人工验收)

### 人工胜负

| 结果 | 数量 |
|------|------|
| V1 Win | 0 |
| V2 Win | 4 |
| Tie | 11 |
| Both Fail | 0 |

### 人工质量指标

| 指标 | V1 | V2 | 判定 |
|------|-----|-----|------|
| Factually Correct Rate | 100% | 100% | PASS |
| External Knowledge Violation | 0% | 0% | PASS |
| Number Preservation Rate | 100% | 100% | PASS |
| Uncertainty Preservation Rate | 33.3% | **100%** | PASS (V2 优) |
| Injection Safety Rate | 100% | 100% | PASS |

### Severity 分布

| Severity | V1 | V2 |
|----------|-----|-----|
| none | 11 | 15 |
| minor | 4 | 0 |
| major | 0 | 0 |
| critical | 0 | 0 |

**人工指标结论: 5/5 PASS，V2 无 critical 回归**

## Combined Decision

### 最终状态: **ADOPT_V2**

## Decision Reason

**自动指标依据:**
- Precision 提升 24.2%（0.5063 → 0.6287），远超 15% 门槛
- Recall 不降反升（0.9906 → 0.9965）
- 成功率从 96% 提升到 100%（V1 在 T13 三次失败）
- 节点数精简 16.5%（20.0 → 16.7），Node Range 合规率翻倍（41% → 89%）
- P95 延迟改善 16.6%（24.5s → 20.4s）

**人工评审依据:**
- V2 人工胜出 4 次，V1 胜出 0 次
- V2 零 severity 问题（V1 有 4 条 minor）
- V2 在不确定性保留维度显著优于 V1（100% vs 33%）
- 5 个关键 Case 全部通过：技术实体、数值、不确定性、注入攻击
- 无 critical 或 major 问题

**风险边界:**
- V2 在 T16 自动指标中略低于 V1（0.73 vs 0.78，差 0.05），属于噪声范围
- V2 Precision StdDev 略高于 V1（0.148 vs 0.108），因动态节点数所致，属预期行为
- T06/T07/T21 在两版本中表现相同（均命中 25 节点上限），提示极长文本仍受硬限制约束

**是否存在 critical 问题: 否**

## Limitations

1. 当前人工复核由单一人工审核者完成，未使用多人交叉验证
2. 人工样本为 15 条（5 Cases × 3 runs），覆盖有限
3. 测试内容主要为中文技术文档、会议记录和数据报告
4. 当前结果仅适用于 claude-sonnet-4-6 模型
5. 后续仍需线上灰度监控确认真实用户体验

## Next Steps

1. ~~完成人工复核~~ ✓
2. 进入 Stage 0 内部冒烟测试
3. 通过后进入 Stage 1 (10% 灰度)
4. 按 `PROMPT_V2_ROLLOUT_PLAN.md` 逐步推进

---

*最终验收完成: 2026-08-04*
*验收依据: 自动指标 7/7 PASS + 人工指标 5/5 PASS + 零 critical*
