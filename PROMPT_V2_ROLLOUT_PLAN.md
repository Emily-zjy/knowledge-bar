# Prompt V2 灰度发布方案

## 前提条件

- [x] 自动指标验收 7/7 PASS
- [ ] 人工复核 5/5 PASS（当前状态: NEEDS_MORE_REVIEW）
- [x] 生产 Prompt 版本机制就绪
- [x] V1 回滚路径确认

**只有人工复核全部通过后，才可进入 Stage 0。**

---

## Stage 0: 开发环境验证

**流量**: 内部测试 100% 使用 V2

**配置**:
```
AI_PROMPT_VERSION=v2
```

**检查清单**:
- [ ] API 成功率 100%（至少 10 次测试请求）
- [ ] Schema Repair 触发率正常
- [ ] Trace 日志正确记录 `prompt_version: v2`
- [ ] 前端渲染正常（节点显示、层级关系、交互）
- [ ] 无 Forbidden 内容
- [ ] 平均节点数在 10-20 范围

**退出条件**: 全部通过 → 进入 Stage 1

---

## Stage 1: 10% 灰度

**持续时间**: 至少 50 次真实生成请求 OR 3 天（取较晚者）

**分流方式**:
```python
import hashlib

def get_prompt_version(user_id: str, rollout_pct: int = 10) -> str:
    h = int(hashlib.md5(user_id.encode()).hexdigest()[:8], 16)
    if (h % 100) < rollout_pct:
        return "v2"
    return "v1"
```

使用 `user_id` 或 `knowledge_base_id` 的稳定哈希分流。
**禁止**每次请求随机分流（避免同一用户体验反复变化）。

**监控门槛**:

| 指标 | 门槛 | 触发动作 |
|------|------|----------|
| Success Rate | >= 97% | 低于则暂停扩量 |
| P95 Latency | <= 22s | 超过则观察 1h |
| Empty Response Rate | <= 2% | 超过则回滚 |
| Forbidden 违规 | = 0 | 任何命中立即回滚 |
| 平均节点数 | 8-22 | 超出则人工检查 |
| Repair Rate | 不高于 V1 | 明显升高则暂停 |

**退出条件**: 50 次请求 + 3 天无异常 → 进入 Stage 2

---

## Stage 2: 50% 灰度

**持续时间**: 至少 100 次真实生成请求 OR 3 天（取较晚者）

**分流**: 将 `rollout_pct` 调整为 50

**增加监控**:

| 指标 | 对比基准 | 告警条件 |
|------|----------|----------|
| 用户重新生成率 | V1 同期 | 上升 > 20% |
| 用户手动删除节点数 | V1 同期 | 显著增加 |
| 用户立即退出率 | V1 同期 | 上升 > 15% |
| V1/V2 失败率对比 | — | V2 高于 V1 |

**退出条件**: 100 次请求 + 3 天 + 无回归 → 进入 Stage 3

---

## Stage 3: 100% 上线

**条件（全部满足）**:
- 自动门槛全部满足
- 无 critical 人工 Bad Case
- 50% 阶段无明显回归
- 运维确认无异常

**配置**:
```
AI_PROMPT_VERSION=v2
```

移除分流逻辑，全量使用 V2。

---

## 线上监控指标

### 质量代理指标（按 prompt_version 分组）

- 每次生成节点数
- Node Range 合规率（节点数在 case 难度对应的合理范围内）
- 用户重新生成率
- 用户手动删除节点数
- 用户修改节点文本数

### 工程指标

- Success Rate
- Empty Response Rate
- Retry Rate（LLM 重试率）
- Repair Rate（Schema 修复率）
- Avg / P50 / P95 Latency
- Token Usage（input/output tokens）

### 安全指标

- Forbidden 内容命中次数
- Prompt Injection 污染检测
- 非法 HTML/Script 输出检测

### 维度

所有指标**必须**按 `prompt_version` 维度分组统计，支持 V1/V2 对比面板。

---

## 回滚方案

### 回滚触发条件（任一满足即回滚）

1. Success Rate < 95%
2. P95 Latency 连续 1h 超过 V1 基线 20%（即 > 29s）
3. 出现 Prompt Injection 污染
4. 出现 critical 事实错误（人工确认）
5. Empty Response Rate > 5%
6. 用户重新生成率较 V1 同期上升 20% 以上

### 回滚操作

```bash
# 修改环境变量
AI_PROMPT_VERSION=v1

# 无需重启应用（如使用热加载配置）
# 否则重启应用即可
```

### 回滚验证

- 确认 Trace 记录恢复为 `prompt_version: v1`
- 确认节点数恢复到 V1 基线（~20 nodes avg）
- 确认 Success Rate 恢复正常

### V1 保留策略

- `PROMPT_V1` 永久保留在 `backend/app/prompts/mindmap_prompts.py`
- `backend/evaluation/prompts/prompt_v1.txt` 作为独立备份
- 回滚只需改一个环境变量，无需修改代码或重新部署
