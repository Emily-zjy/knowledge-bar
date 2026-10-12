# Prompt V2 — Stage 1 Implementation Report

## 状态: COMPLETE

## 实现概览

Stage 1 实现了基于 SHA-256 稳定哈希的 10% 灰度分流，确保同一用户/知识库在整个灰度期间始终命中同一 Prompt 版本。

## 修改文件

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `backend/app/prompts/rollout.py` | 新建 | 稳定哈希分流核心逻辑 |
| `backend/app/core/config.py` | 修改 | 新增 3 个 rollout 配置字段 |
| `backend/app/services/ai_mindmap.py` | 修改 | 集成 rollout resolver + trace metadata |
| `backend/.env.example` | 修改 | 文档化新环境变量 |
| `backend/tests/test_rollout.py` | 新建 | 13 个单元测试 |

## 核心设计

### 1. 稳定哈希分流 (`rollout.py`)

```python
def _stable_bucket(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100  # 0-99 均匀分布
```

- 使用 SHA-256 前 8 位 hex（32 bit）取模 100
- 同一 key 永远落入同一 bucket
- 跨进程、跨重启一致
- 不使用 Python 内置 `hash()`（每次启动 seed 不同）

### 2. 分流决策 (`resolve_prompt_version`)

优先级:
1. `override_version` → 强制使用指定版本（测试/管理用）
2. `percentage == 0` → 全部走 fallback
3. `percentage >= 100` → 全部走 v2
4. `bucket < percentage` → v2，否则 fallback

Key 选择: `user_id` > `knowledge_base_id` > fallback

### 3. 配置字段

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `AI_PROMPT_V2_PERCENTAGE` | 0 | V2 流量百分比（0-100） |
| `AI_PROMPT_FALLBACK_VERSION` | v1 | 非 V2 流量使用的版本 |
| `AI_PROMPT_ROLLOUT_MODE` | stable_hash | 分流模式 |

### 4. Trace 记录

每条 trace 新增字段:

| 字段 | 类型 | 示例值 |
|------|------|--------|
| `prompt_version` | string | "v2" |
| `prompt_assignment_mode` | string | "stable_hash" |
| `prompt_rollout_percentage` | int | 10 |
| `prompt_bucket` | int | 37 |
| `prompt_assignment_key_type` | string | "knowledge_base_id" |

### 5. `generate_mind_map` 集成

```python
version, rollout_meta = resolve_prompt_version(
    user_id=None,
    knowledge_base_id=payload.knowledge_base_id,
)
messages = _build_prompt(payload, version)
```

- `_build_prompt` 新增 `version` 参数
- `_save_trace` 新增 `rollout_meta` 和 `prompt_version` 参数
- 所有错误路径均传递 rollout metadata

## 测试结果

### 单元测试: 13/13 PASS

```
tests/test_rollout.py::TestStableBucket::test_deterministic PASSED
tests/test_rollout.py::TestStableBucket::test_range PASSED
tests/test_rollout.py::TestStableBucket::test_matches_raw_sha256 PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_01_percentage_zero_returns_fallback PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_02_percentage_100_returns_v2 PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_03_percentage_10_stable_assignment PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_04_same_key_always_same_version PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_05_cross_process_determinism PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_06_no_key_falls_back PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_07_explicit_override PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_08_invalid_percentage_clamped PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_09_user_id_priority_over_kb_id PASSED
tests/test_rollout.py::TestResolvePromptVersion::test_10_trace_metadata_fields_complete PASSED
```

### 回归测试: 26/26 PASS

```
tests/test_p0_blockers.py — 22 passed
tests/test_api_mindmap.py — 4 passed
```

## 灰度启动方式

```bash
# 10% 灰度
AI_PROMPT_V2_PERCENTAGE=10

# 紧急回滚到 0%
AI_PROMPT_V2_PERCENTAGE=0

# 全量 V2
AI_PROMPT_V2_PERCENTAGE=100
```

无需重启应用（如果使用支持热加载的部署方式），否则修改 `.env` 后重启即可。

## 安全边界

- percentage < 0 → clamped to 0（全 V1）
- percentage > 100 → clamped to 100（全 V2）
- 无 key（user_id 和 knowledge_base_id 均为 None）→ fallback
- override 仅影响单次请求，不修改全局状态

## 遗留事项

- `user_id` 当前传入 `None`（尚无 auth → user_id 提取逻辑）
- 实际路由 key 为 `knowledge_base_id`
- 后续如需按用户维度分流，可从 authorization token 提取 user_id

---

*实现完成: 2026-08-04*
*测试通过: 13 rollout + 26 regression = 39/39 PASS*
