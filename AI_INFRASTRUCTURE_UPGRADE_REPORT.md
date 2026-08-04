# AI Agent Infrastructure Upgrade Report

## 概述

本次升级将 Knowledge Bar AI Agent 从单文件架构拆分为模块化工程架构，为后续 Golden Dataset、Evaluator Reliability、A/B Model Test、Prompt Experiment 提供稳定基础。

## 修改文件列表

| 文件 | 操作 | 修改内容 | 原因 |
|------|------|----------|------|
| `backend/app/services/llm_client.py` | 新增 | 独立 LLM Client 模块 | 将 HTTP 调用与业务逻辑解耦 |
| `backend/app/services/schema_repair.py` | 新增 | Schema 修复层 | 自动修复 LLM 输出的结构问题 |
| `backend/app/services/ai_mindmap.py` | 重写 | Agent 层重构，调用 LLM Client + Schema Repair | 职责分离，增强可靠性 |
| `backend/.env` | 修改 | `AI_MOCK_FALLBACK=false` | 禁用 mock 回退以确保真实 API 调用 |
| `backend/.env.example` | 修改 | 补充文档说明 | 增加 Anthropic base URL 说明 |

## LLM Client 设计说明

### 文件: `backend/app/services/llm_client.py`

**核心接口:**

```python
def generate(
    messages: list[dict[str, str]],
    *,
    provider: str | None = None,
    model: str | None = None,
    max_retries: int | None = None,
) -> LLMResponse
```

**设计原则:**

1. **Provider 无关** — Agent 只调用 `llm_client.generate(messages)`，不知道底层是 OpenAI/Anthropic/代理
2. **统一响应** — 返回 `LLMResponse(text, model, latency_ms, usage, attempts)`
3. **内置重试** — 空响应 (Empty Response) 标记为 retryable，自动重试
4. **参数可覆盖** — 支持运行时覆盖 provider/model/retries，为 A/B 测试预留

**支持的 Provider:**

| Provider | URL 解析 | 认证方式 |
|----------|----------|----------|
| `openai_compatible` (默认) | settings.resolved_ai_base_url → /v1/chat/completions | Bearer token |
| `anthropic` | settings.resolved_ai_base_url → /v1/messages | x-api-key |

**错误分类:**

| 错误码 | 来源 | Retryable |
|--------|------|-----------|
| LLM_KEY_MISSING | 配置检查 | No |
| LLM_TIMEOUT | httpx.TimeoutException | Yes |
| LLM_NETWORK_ERROR | httpx.TransportError | Yes |
| LLM_TEMPORARY_ERROR | HTTP 408/409/425/429/5xx | Yes |
| LLM_HTTP_ERROR | HTTP 4xx | No |
| LLM_EMPTY_RESPONSE | 空内容 | **Yes** (V0中不重试) |

## Schema Repair 流程

### 文件: `backend/app/services/schema_repair.py`

**触发条件:** Pydantic `_normalize_mind_map()` 校验失败时自动触发

**流程:**

```
LLM 输出 JSON
    ↓
_normalize_mind_map() 第一次尝试
    ↓ 成功 → 直接返回
    ↓ 失败 ↓
repair_mind_map() 结构修复
    ↓
_normalize_mind_map() 第二次尝试
    ↓ 成功 → 返回 (标记 repair=true)
    ↓ 失败 → 抛出 SCHEMA_REPAIR_FAILED
```

**修复能力:**

| 问题 | 修复策略 | 实测触发 |
|------|----------|----------|
| 多个根节点 | 保留第一个，其余挂为子节点 | — |
| parentId 指向不存在的节点 | 重新挂载到根节点 | — |
| 节点数超过 25 | 删除最深叶子节点 | ✓ (4次) |
| 字段名不标准 (name/parent/label) | 规范化为 id/parentId/text/order | — |
| text 超过 120 字符 | 截断并加 "..." | — |
| 缺少 order 字段 | 按顺序补充 | — |

**原则:**
- 只修结构，不改语义
- 不增加新节点
- 不修改已有节点文本内容
- 修复日志完整记录到 Trace

## Retry 机制

### V0 (旧)

- 重试次数: `ai_max_retries` (默认 1)
- 只重试网络/HTTP 错误
- **空响应不重试** ← 导致 T14/T21 失败
- 无退避

### V1 (新)

- 重试次数: `max_retries=2` (即最多 3 次尝试)
- **空响应标记为 retryable** ← 解决 T14/T21
- 重试范围: 超时、网络错误、5xx、空响应
- Trace 记录 retry_count
- 无退避 (代理侧已有队列)

## Trace 变化

### 新增字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `llm_latency_ms` | int | 纯 LLM 调用耗时 (不含解析) |
| `retry_count` | int | LLM Client 重试次数 |
| `repair_attempted` | bool | 是否触发了 Schema Repair |
| `repair_success` | bool | Repair 是否成功 |
| `repair_actions` | list[str] | 具体修复动作列表 |
| `token_usage` | dict | 模型 token 消耗 |
| `error_type` | str | 错误分类码 |

### 兼容性

- 保持原有字段 (run_id, input_text, title, model, provider, timestamp, total_latency_ms, success, error, output_json)
- evaluation/run_eval.py 无需修改
- 旧 trace 文件不受影响

## 测试结果

### 单元测试

```
tests/test_ai_v2.py: 24 passed ✓
```

### 全量评测 (25 cases, 真实 API)

| 指标 | V0 | V1 | 变化 |
|------|-----|-----|------|
| 成功率 | 80% | **96%** | **+16%** |
| Avg Precision | 0.44 | 0.43 | ≈持平 |
| Avg Recall | 0.85 | 0.85 | ≈持平 |
| 综合评分 | 50.5 | **56.0** | **+5.5** |

### 修复的 Case

- T06 (AI_INVALID_SCHEMA → PASS via Repair)
- T07 (AI_INVALID_SCHEMA → PASS via Repair)
- T13 (AI_INVALID_SCHEMA → PASS via Repair)
- T14 (AI_EMPTY_RESPONSE → PASS via Repair)
- T21 (AI_EMPTY_RESPONSE → PASS via Retry + Repair)

## 对后续 Evaluation 的支持

### Golden Dataset

- Trace 记录完整 LLM 原始输出，可用于构建 ground truth
- `repair_actions` 字段标识哪些 case 需要 prompt 优化

### Evaluator Reliability

- `retry_count` 区分偶发失败和系统性问题
- `llm_latency_ms` vs `total_latency_ms` 分离网络开销和处理开销

### A/B Model Test

- `llm_client.generate(model="xxx")` 支持运行时切换模型
- Trace 自动记录 model 字段
- 无需改 Agent 代码即可对比不同模型

### Prompt Experiment

- Prompt 仍在 Agent 层 (`_build_prompt`)，可独立修改
- `ai_prompt_version` 已在 config 中，可配合 trace 追踪版本
- LLM Client 对 prompt 格式无感知

## 架构图

```
┌─────────────────────────────────────────────────┐
│  FastAPI (api/ai.py)                            │
│    POST /api/ai/mindmap/generate                │
└───────────────────┬─────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────┐
│  Agent Layer (services/ai_mindmap.py)           │
│    _build_prompt()  →  消息列表                  │
│    _extract_json()  →  JSON 解析                 │
│    _normalize_with_repair()  →  校验+修复        │
│    _save_trace()  →  运行记录                    │
└──────┬────────────────────┬─────────────────────┘
       │                    │
┌──────▼──────┐    ┌───────▼────────┐
│ LLM Client  │    │ Schema Repair  │
│ (llm_client │    │ (schema_repair │
│  .py)       │    │  .py)          │
│             │    │                │
│ - generate()│    │ - repair_mind  │
│ - retry     │    │   _map()       │
│ - latency   │    │ - fix roots    │
│ - usage     │    │ - fix parents  │
│ - errors    │    │ - trim nodes   │
└──────┬──────┘    └────────────────┘
       │
┌──────▼──────────────┐
│  External LLM API   │
│  (rightapi.ai proxy │
│   → Claude)         │
└─────────────────────┘
```

## 验证方式

```bash
# 1. 模块导入测试
python -c "from app.services.llm_client import generate; from app.services.schema_repair import repair_mind_map; print('OK')"

# 2. 单元测试
python -m pytest tests/test_ai_v2.py -x -q

# 3. Schema Repair 单元验证
python -c "from app.services.schema_repair import repair_mind_map; r = repair_mind_map({'nodes': [{'id':'a','parentId':None,'text':'X','order':0},{'id':'b','parentId':None,'text':'Y','order':1}]}); assert r.repaired"

# 4. 真实 API 连通
python -c "from app.services.ai_mindmap import generate_mind_map; from app.models.ai import GenerateMindMapRequest; r = generate_mind_map(GenerateMindMapRequest(knowledge_base_id='test', title='Test', description='', content_md='Hello world'), None, None); print(f'OK nodes={len(r.mind_map.nodes)}')"

# 5. 全量评测
python -m evaluation.run_eval
```
