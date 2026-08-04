# Prompt V2 — Stage 1 配置审计

## 审计日期: 2026-08-04

## 审计目标

确认 10% 灰度启动前，不存在会强制全量 V2 的配置覆盖路径。

---

## 1. AI_PROMPT_VERSION 配置检查

| 项目 | 值 |
|------|-----|
| config.py 默认值 | `p0-mindmap-v1` |
| 映射目标 | V1（`_VERSIONS["p0-mindmap-v1"] = PROMPT_V1`） |
| .env.example 文档值 | `v1` |

**是否会覆盖灰度分流？** 否。

原因：`generate_mind_map()` 调用 `resolve_prompt_version()` 获取版本，然后显式传入 `_build_prompt(payload, version)`。`_build_prompt` 的 `version` 参数有值时不会 fallback 到 `settings.ai_prompt_version`。

**代码路径验证：**

```python
# ai_mindmap.py generate_mind_map()
version, rollout_meta = resolve_prompt_version(
    user_id=None,
    knowledge_base_id=payload.knowledge_base_id,
)
messages = _build_prompt(payload, version)  # version 总是非 None
```

```python
# ai_mindmap.py _build_prompt()
def _build_prompt(payload, version: str | None = None):
    system = get_mindmap_prompt(version or settings.ai_prompt_version)
    # version 来自 resolve_prompt_version，总是 "v1" 或 "v2"
```

**结论：AI_PROMPT_VERSION 不会覆盖灰度。无需删除或修改。**

---

## 2. override_version 暴露检查

| 检查项 | 结果 |
|--------|------|
| API 路由是否接受 override_version 参数 | 否 |
| Request body 是否包含 prompt_version 字段 | 否 |
| 任何 Header 是否传递 override 信息 | 否 |
| generate_mind_map 参数是否包含 override | 否 |

**结论：普通用户请求无法传入 override_version。该参数仅在 `resolve_prompt_version()` 函数签名中存在，供内部测试使用。**

---

## 3. resolve_prompt_version 唯一性检查

生产请求调用链：

```
API Route (ai.py)
  → generate_mind_map(payload, authorization, guest_session_id)
    → resolve_prompt_version(user_id=None, knowledge_base_id=payload.knowledge_base_id)
    → _build_prompt(payload, version)  ← 使用 rollout 结果
```

| 调用路径 | 是否使用 resolve_prompt_version |
|----------|-------------------------------|
| POST /ai/mindmap/generate | 是 |
| POST /ai/mindmap/{kb_id}/regenerate | 是（经由 generate_mind_map） |

**结论：resolve_prompt_version 是所有生产 AI 请求的唯一版本决策来源。**

---

## 4. 残留 settings.ai_prompt_version 使用

| 文件 | 行 | 用途 | 风险 |
|------|-----|------|------|
| `ai_mindmap.py:67` | `_build_prompt` fallback | 无风险（version 参数总是非 None） |
| `ai_mindmap.py:188` | `_save_trace` fallback | 无风险（prompt_version 参数总是传入） |
| `supabase_store.py:125` | `create_generation_job` | **低风险：记录不准确** |

**supabase_store.py:125 详情：**

`create_generation_job` 将 `settings.ai_prompt_version`（固定为 `p0-mindmap-v1`）写入 job 记录。这不影响实际 prompt 选择，但 job 表中的 `prompt_version` 字段将始终显示 `p0-mindmap-v1`，与 trace 中实际使用的版本不一致。

**建议（非阻塞）：** 后续迭代中将 resolved version 传递到 job 记录。当前不修改，因为：
- 不影响灰度分流逻辑
- 不影响用户体验
- Trace 文件中已有准确的 `prompt_version` 字段

---

## 5. Stage 1 必需配置

| 变量 | 必需值 | 当前默认值 | 状态 |
|------|--------|-----------|------|
| AI_PROMPT_V2_PERCENTAGE | 10 | 0 | 需在 Railway 设置为 10 |
| AI_PROMPT_FALLBACK_VERSION | v1 | v1 | 正确 |
| AI_PROMPT_ROLLOUT_MODE | stable_hash | stable_hash | 正确 |
| AI_PROMPT_VERSION | 不影响 | p0-mindmap-v1 | 安全（不覆盖灰度） |

---

## 6. 审计结论

| 风险项 | 状态 |
|--------|------|
| AI_PROMPT_VERSION 覆盖灰度 | **不存在** |
| 用户可传入 override_version | **不存在** |
| resolve_prompt_version 被绕过 | **不存在** |
| 全量 V2 配置泄露 | **不存在** |
| Job 表 prompt_version 不准确 | 存在但不影响分流（低优先级） |

**可安全启动 10% 灰度。**

---

*审计完成: 2026-08-04*
