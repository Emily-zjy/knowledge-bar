# Prompt V2 — Stage 1 Railway 部署操作说明

## 前置条件

- Stage 0 冒烟测试已通过 (5/5 PASS)
- 分流逻辑已验证 (6/6 PASS)
- 配置审计已确认无全量覆盖风险
- 回滚方案已就绪

---

## 步骤 1: 设置 Railway 环境变量

在 Railway Dashboard → 项目 → Backend Service → Variables 中添加/修改:

```
AI_PROMPT_V2_PERCENTAGE=10
AI_PROMPT_FALLBACK_VERSION=v1
AI_PROMPT_ROLLOUT_MODE=stable_hash
```

### 检查 AI_PROMPT_VERSION

确认 `AI_PROMPT_VERSION` 的值:

| 当前值 | 操作 |
|--------|------|
| `v1` 或 `p0-mindmap-v1` | 无需修改（不会覆盖灰度） |
| `v2` | **必须改为 `v1` 或删除**（否则全量 V2） |
| 不存在 | 正常（默认 `p0-mindmap-v1`，映射到 V1） |

> 注意: `AI_PROMPT_VERSION` 不影响灰度分流逻辑（已通过配置审计确认），但如果在某些非主流调用路径中被使用，保持为 v1 最安全。

---

## 步骤 2: 重新部署

Railway 环境变量修改后:

- 如果项目设置为「变量修改自动触发重新部署」→ 等待部署完成
- 如果需要手动触发 → 点击 "Redeploy" 或推送一个空 commit

等待部署状态变为 **Active**。

---

## 步骤 3: 验证服务正常

调用 health 接口:

```bash
curl -s https://<your-railway-domain>/health | jq .
```

预期响应:
```json
{
  "status": "ok"
}
```

---

## 步骤 4: 冒烟生成请求 (至少 10 次)

使用不同的 knowledge_base_id 发起生成请求:

```bash
# 替换 <TOKEN> 和 <KB_ID>
curl -X POST https://<your-railway-domain>/ai/mindmap/generate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <TOKEN>" \
  -d '{
    "knowledge_base_id": "<KB_ID>",
    "title": "Stage 1 Smoke Test",
    "description": "灰度冒烟验证",
    "content_md": "Python 是一种高级编程语言。它支持面向对象、函数式和过程式编程。主要特点包括动态类型、自动内存管理和丰富的标准库。"
  }'
```

建议使用至少 10 个不同的 knowledge_base_id 以验证分流覆盖。

---

## 步骤 5: 检查 Trace

检查生成的 Trace 文件（`evaluation/runs/*.json`）:

```bash
# SSH 或 Railway CLI 进入容器后:
ls -la evaluation/runs/ | tail -20

# 查看最新 trace 的 prompt_version 和 rollout 字段
cat evaluation/runs/<latest-run-id>.json | python -m json.tool | grep -E "prompt_version|prompt_assignment|prompt_bucket|prompt_rollout"
```

**预期结果:**

在 10 次请求中:
- 大约 1-2 次显示 `"prompt_version": "v2"`
- 大约 8-9 次显示 `"prompt_version": "v1"`
- 所有 trace 包含完整 rollout metadata

如果 10 次全部为 v1:
- 正常现象（10% 概率下 10 次全 V1 的概率 = 0.9^10 ≈ 35%）
- 可增加请求数到 30 次再观察
- 或检查使用的 knowledge_base_id 的 bucket 值

验证特定 ID 的 bucket:

```python
import hashlib
kb_id = "your-knowledge-base-id"
bucket = int(hashlib.sha256(kb_id.encode("utf-8")).hexdigest()[:8], 16) % 100
print(f"bucket={bucket}, version={'v2' if bucket < 10 else 'v1'}")
```

---

## 步骤 6: 确认灰度已生效

检查清单:

- [ ] Railway 环境变量已设置 `AI_PROMPT_V2_PERCENTAGE=10`
- [ ] 服务已重新部署且状态为 Active
- [ ] Health 接口返回正常
- [ ] 至少执行 10 次冒烟生成
- [ ] Trace 中包含 rollout metadata 字段
- [ ] Trace 中存在 v1 和 v2（或解释小样本未命中的原因）
- [ ] 无 500 错误或异常

---

## 紧急回滚

如果观察到异常:

```
Railway Dashboard → Variables:
AI_PROMPT_V2_PERCENTAGE=0
```

触发重新部署后，所有请求回到 V1。

回滚耗时: 变量修改 + 部署 ≈ 1-3 分钟。

---

*操作说明生成: 2026-08-04*
