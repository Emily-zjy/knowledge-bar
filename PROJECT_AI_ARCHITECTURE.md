# Knowledge Bar — AI 架构分析文档

## 1. 项目目录结构

```
knowledge-bar/
├── backend/
│   ├── app/
│   │   ├── main.py                    # FastAPI 入口，注册路由
│   │   ├── api/
│   │   │   ├── ai.py                  # V2 API 路由 (活跃，/api/ai/*)
│   │   │   └── mindmap.py             # V0 API 路由 (未挂载，遗留)
│   │   ├── core/
│   │   │   └── config.py              # pydantic-settings 配置，读取 .env
│   │   ├── models/
│   │   │   ├── ai.py                  # V2 Pydantic 模型 (Request/Response/MindMapData)
│   │   │   └── mindmap.py             # V0 Pydantic 模型 (遗留)
│   │   ├── services/
│   │   │   ├── ai_mindmap.py          # V2 LLM 调用核心 (活跃)
│   │   │   ├── mindmap_agent.py       # V0 Agent 管线 (遗留，未挂载)
│   │   │   ├── actions.py             # 纯函数：prepare_text, chunk_text, validate, render
│   │   │   ├── auth.py                # Supabase JWT 验证
│   │   │   └── supabase_store.py      # Supabase 数据持久化
│   │   └── db/
│   │       └── store.py               # SQLite (V0 遗留)
│   ├── evaluation/
│   │   ├── run_eval.py                # 评测执行器
│   │   ├── generate_report.py         # 报告生成器
│   │   ├── test_cases.json            # 25 个评测 Case
│   │   └── runs/                      # Trace 记录目录
│   ├── tests/                         # pytest 测试套件
│   ├── .env                           # 环境变量 (已配置真实 API)
│   └── .env.example                   # 环境变量模板
├── frontend/
│   ├── src/
│   │   ├── App.tsx                    # 路由入口
│   │   ├── pages/
│   │   │   └── MindMapPage.tsx        # 思维导图页面
│   │   ├── lib/
│   │   │   ├── api.ts                 # 后端 API 调用层
│   │   │   ├── supabase.ts            # Supabase 客户端
│   │   │   ├── cloudStore.ts          # 云端状态管理
│   │   │   └── guestStore.ts          # 游客模式
│   │   ├── components/                # UI 组件
│   │   └── types.ts                   # TypeScript 类型定义
│   └── vite.config.ts
└── supabase/
    └── migrations/                    # 数据库迁移
```

## 2. 当前 AI 调用链路

```
用户输入 (前端 MindMapPage.tsx)
  ↓
前端 api.ts :: generateMindMap()
  ↓ POST /api/ai/mindmap/generate
后端 api/ai.py :: generate_mindmap() [line 153]
  ↓ 鉴权 + 获取知识库内容
services/ai_mindmap.py :: generate_mind_map() [line 264]
  ↓ 路由: settings.ai_provider
  ├─ "mock" → _fallback_mind_map() (确定性，无LLM)
  ├─ "anthropic" → _request_anthropic() [line 195]
  │     ↓ httpx POST → _anthropic_messages_url()
  │     ↓ Headers: x-api-key, anthropic-version
  └─ 其他 → _request_openai_compatible() [line 148]
        ↓ httpx POST → _chat_completions_url()
        ↓ Headers: Authorization: Bearer
              ↓
_build_prompt() [line 55] — 组装 system + user 消息
              ↓
HTTP 响应 → _extract_json() → _normalize_mind_map()
              ↓
Pydantic 校验: MindMapData(title, nodes[])
              ↓
_save_trace() → evaluation/runs/{run_id}.json
              ↓
返回 GenerateMindMapResult → api/ai.py
              ↓
supabase_store.save_mind_map() → 持久化
              ↓
JSON Response → 前端渲染
```

## 3. 关键文件位置

| 角色 | 文件 | 关键函数/类 |
|------|------|------------|
| FastAPI 入口 | `backend/app/main.py` | `app = FastAPI()` |
| API 路由 | `backend/app/api/ai.py` | `generate_mindmap()`, `regenerate_mindmap()` |
| LLM 调用核心 | `backend/app/services/ai_mindmap.py` | `generate_mind_map()`, `_request_anthropic()`, `_request_openai_compatible()` |
| Prompt 组装 | `backend/app/services/ai_mindmap.py:55` | `_build_prompt()` |
| 结果校验 | `backend/app/services/ai_mindmap.py:122` | `_normalize_mind_map()` |
| 配置 | `backend/app/core/config.py` | `class Settings` |
| Pydantic 模型 | `backend/app/models/ai.py` | `GenerateMindMapRequest`, `MindMapData`, `MindMapNode` |
| 前端 API 层 | `frontend/src/lib/api.ts` | `generateMindMap()` |
| 评测执行器 | `backend/evaluation/run_eval.py` | `run_evaluation()` |
| V0 Agent (遗留) | `backend/app/services/mindmap_agent.py` | `generate_mindmap_pipeline()` |

## 4. 当前状态判断

**状态：A — 已经接入真实 API**

| 维度 | 状态 |
|------|------|
| LLM 调用代码 | 已存在，httpx 直接调 HTTP (无 SDK) |
| Provider | `openai_compatible` (代理 rightapi.ai → Claude) |
| 模型 | `claude-sonnet-4-6` |
| Mock | 存在 `_fallback_mind_map()`，但当前 `AI_MOCK_FALLBACK=false` |
| 真实调用验证 | 已通过，延迟 4-6 秒，返回正确多层中文思维导图 |
| Trace | 已实现，保存至 `evaluation/runs/` |

## 5. 技术细节

### LLM 调用方式

- **不使用 SDK**：无 Anthropic SDK、无 OpenAI SDK、无 LangChain、无 LiteLLM
- **直接 HTTP**：通过 `httpx.Client.post()` 调用
- 支持两种模式：
  - `openai_compatible`：OpenAI Chat Completions 格式 (支持任何兼容代理)
  - `anthropic`：Claude Messages API 原生格式 (支持自定义 base URL)

### Prompt 设计

- System prompt (英文)：指示生成思维导图 JSON，限制 25 节点，不虚构
- User prompt：`title + description + content_md`
- 温度：0.2
- 响应格式：要求 JSON Object

### 校验规则

- Pydantic `MindMapData.model_validate()`
- 最大 25 节点
- 恰好 1 个根节点 (parentId=null)
- 所有 parentId 必须指向已有节点
- 最大深度 6 层
- 无重复 ID

### 重试机制

- 可重试错误：超时、网络错误、HTTP 408/409/425/429/5xx
- 最大重试次数：`ai_max_retries` (当前 1 次)
- Mock 回退：配置为 false 时不回退

## 6. 遗留系统 (V0 Agent)

文件 `backend/app/services/mindmap_agent.py` 包含更复杂的管线：

```
prepare_text → chunk_text → _generate_with_llm → validate_mindmap → _fix_with_llm → render_mindmap
```

特点：
- 中文 Prompt，要求 source_ids 溯源
- 校验失败自动修复 (最多 2 次)
- 使用 SQLite 持久化
- **未挂载**（main.py 明确注释不注册 V0 路由）

## 7. 后续 AI Agent 自动化评测接入建议

### 已具备条件

1. 25 个评测 Case (`evaluation/test_cases.json`)
2. 评测执行器 (`evaluation/run_eval.py`)
3. Precision/Recall/FP 指标体系
4. Trace 日志 (每次调用保存 JSON)
5. 真实 API 已通

### 建议下一步

| 优先级 | 任务 | 说明 |
|--------|------|------|
| P0 | 跑真实评测 | `python -m evaluation.run_eval` 替代 mock baseline |
| P0 | 完善 Prompt | 当前 prompt 对简短输入生成节点过少 (≤4)，需增加层级深度指令 |
| P1 | 增加延迟分解 | 在 trace 中区分网络/LLM生成/解析各阶段耗时 |
| P1 | A/B Prompt 测试 | 对比不同 prompt 版本的 P/R 差异 |
| P2 | CI 集成 | 在 PR 时自动跑子集 Case，防止 prompt 回归 |
| P2 | 复用 V0 管线思路 | V0 的校验+自动修复循环可提升鲁棒性 |
| P3 | 流式输出 | 减少用户感知延迟 (当前 4-6 秒) |

### 评测命令

```bash
cd backend

# 真实 API 全量评测
python -m evaluation.run_eval

# 指定 Case
python -m evaluation.run_eval --cases T01,T05,T08

# Mock baseline
python -m evaluation.run_eval --provider mock

# 生成报告
python -m evaluation.generate_report
```
