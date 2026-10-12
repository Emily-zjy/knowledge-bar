# Prompt V2 — Stage 1 最终汇报

## 日期: 2026-08-04

---

## 配置审计结果

| 项目 | 结论 |
|------|------|
| 是否存在全量 V2 覆盖风险 | **不存在** |
| AI_PROMPT_VERSION 是否覆盖灰度 | 否（`p0-mindmap-v1` 映射到 V1，且 rollout resolver 优先） |
| override_version 是否对外暴露 | 否（API 层无此参数） |
| resolve_prompt_version 是否唯一决策源 | 是 |
| supabase_store job 记录 | 低风险：写入固定 `p0-mindmap-v1`，不影响分流 |

详见: [PROMPT_V2_STAGE1_CONFIG_AUDIT.md](PROMPT_V2_STAGE1_CONFIG_AUDIT.md)

---

## 当前 Rollout 配置

| 变量 | 值 |
|------|-----|
| 当前 rollout key | `knowledge_base_id` |
| 当前灰度比例 | 10%（`AI_PROMPT_V2_PERCENTAGE=10`） |
| Fallback 版本 | v1 |
| 分流模式 | stable_hash (SHA-256) |

---

## 分桶冒烟结果

| 测试项 | 结果 |
|--------|------|
| 100 ID 分布 | V1: 85, V2: 15 (15%，在 10% ± 2σ 内) |
| 每 ID × 10 次重复稳定性 | 1000/1000 一致 |
| 跨进程 SHA-256 一致性 | 100/100 匹配 |
| Bucket 范围 [0, 99] | 全部合规 |
| bucket<10 → v2, bucket>=10 → v1 | 100% 一致 |
| 无 key 安全回退 | v1, bucket=-1 |
| **总计** | **6/6 PASS** |

详见: [PROMPT_V2_STAGE1_ASSIGNMENT_SMOKE_REPORT.md](PROMPT_V2_STAGE1_ASSIGNMENT_SMOKE_REPORT.md)

---

## Railway 配置状态

| 项目 | 状态 |
|------|------|
| Railway 是否已配置 | **待操作** |
| 操作说明已生成 | 是 |

详见: [PROMPT_V2_STAGE1_RAILWAY_DEPLOY.md](PROMPT_V2_STAGE1_RAILWAY_DEPLOY.md)

> Railway 环境变量设置需要人工登录 Dashboard 执行。代码和配置已就绪。

---

## 当前状态

### **PREPRODUCTION_CANARY**

原因:
- 灰度代码已实现并通过所有测试
- 分流逻辑已验证正确
- Railway 尚未设置 `AI_PROMPT_V2_PERCENTAGE=10`
- 无真实用户流量经过 V2 路径

---

## 流量统计

| 指标 | 值 |
|------|-----|
| V1 请求数（历史 trace） | 303 |
| V2 请求数（Stage 0 smoke） | 5 |
| 实际 V2 比例 | N/A（无 rollout metadata，均为冒烟测试） |
| 是否满足 72 小时 | 否 |
| 是否达到 50 条 V2 请求 | 否（当前 5 条） |

---

## 当前决策

### **NEEDS_MORE_DATA**

Stage 1 需在 Railway 部署后开始计时。满足以下条件方可进入验收:
1. 持续至少 72 小时
2. V2 真实请求数至少 50 条

---

## 修改文件

| 文件 | 操作 |
|------|------|
| `backend/app/prompts/rollout.py` | 新建 — 稳定哈希分流逻辑 |
| `backend/app/core/config.py` | 修改 — 新增 3 个 rollout 配置字段 |
| `backend/app/services/ai_mindmap.py` | 修改 — 集成 rollout + trace metadata |
| `backend/.env.example` | 修改 — 文档化 rollout 变量 |
| `backend/tests/test_rollout.py` | 新建 — 13 个单元测试 |
| `backend/evaluation/rollout/__init__.py` | 新建 — 包初始化 |
| `backend/evaluation/rollout/stage1_metrics.py` | 新建 — 每日监控脚本 |
| `PROMPT_V2_STAGE1_CONFIG_AUDIT.md` | 新建 — 配置审计报告 |
| `PROMPT_V2_STAGE1_MONITORING_TEMPLATE.md` | 重写 — 修正阈值和指标 |
| `PROMPT_V2_STAGE1_ASSIGNMENT_SMOKE_REPORT.md` | 新建 — 分桶冒烟报告 |
| `PROMPT_V2_STAGE1_RAILWAY_DEPLOY.md` | 新建 — 部署操作说明 |
| `PROMPT_V2_STAGE1_IMPLEMENTATION_REPORT.md` | 新建 — 实现报告 |

---

## 验证命令

```bash
# 单元测试
cd backend && python -m pytest tests/test_rollout.py -v

# 回归测试
cd backend && python -m pytest tests/test_p0_blockers.py tests/test_api_mindmap.py -v

# 每日监控脚本
cd backend && python -m evaluation.rollout.stage1_metrics

# 验证特定 ID 的分桶
python -c "
import hashlib
kb_id = 'your-knowledge-base-id'
bucket = int(hashlib.sha256(kb_id.encode('utf-8')).hexdigest()[:8], 16) % 100
print(f'bucket={bucket}, version={\"v2\" if bucket < 10 else \"v1\"}')
"
```

---

## 下一步

1. 登录 Railway Dashboard，设置 `AI_PROMPT_V2_PERCENTAGE=10`
2. 重新部署服务
3. 执行冒烟请求验证 trace 中包含 rollout metadata
4. 开始 72 小时观察窗口
5. 每日运行 `stage1_metrics.py` 检查指标
6. 累计 50 条 V2 请求后进入 Stage 1 最终验收

---

*汇报生成: 2026-08-04*
