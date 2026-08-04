# Prompt V2 生产集成报告

## 集成架构

```
.env (AI_PROMPT_VERSION=v1|v2)
    ↓
app/core/config.py (settings.ai_prompt_version)
    ↓
app/prompts/mindmap_prompts.py (get_mindmap_prompt)
    ↓
app/services/ai_mindmap.py (_build_prompt)
    ↓
Trace (prompt_version field)
```

## 修改清单

| 文件 | 修改内容 |
|------|----------|
| `backend/app/prompts/__init__.py` | 新增：空 init |
| `backend/app/prompts/mindmap_prompts.py` | 新增：PROMPT_V1, PROMPT_V2, get_mindmap_prompt() |
| `backend/app/services/ai_mindmap.py` | 修改：_build_prompt 使用 get_mindmap_prompt |
| `backend/app/services/ai_mindmap.py` | 修改：trace 记录 prompt_version |
| `backend/.env.example` | 修改：AI_PROMPT_VERSION 文档 |

## 版本切换方式

```bash
# 使用 V1（默认，当前生产）
AI_PROMPT_VERSION=v1

# 使用 V2（人工复核通过后）
AI_PROMPT_VERSION=v2

# 兼容旧配置值
AI_PROMPT_VERSION=p0-mindmap-v1  # 等同于 v1
```

## 验证命令

```bash
cd backend

# 验证 prompt 模块加载
python -c "from app.prompts.mindmap_prompts import get_mindmap_prompt; print(get_mindmap_prompt('v1')[:50])"

# 验证完整调用链（需要 .env 配置）
python -c "from app.core.config import settings; from app.prompts.mindmap_prompts import get_mindmap_prompt; print(f'Version: {settings.ai_prompt_version}'); print(f'Prompt: {get_mindmap_prompt(settings.ai_prompt_version)[:80]}...')"

# 运行现有测试
python -m pytest tests/ -x -q
```

## 安全保证

1. **默认保持 V1**: `config.py` 默认值为 `p0-mindmap-v1`（映射到 V1）
2. **V1 永不删除**: PROMPT_V1 常量保留在代码中
3. **回滚无需部署**: 修改环境变量即可切回 V1
4. **Trace 可追溯**: 每次生成记录使用的 prompt_version
5. **无 monkey-patch**: 生产代码不使用实验时的 monkey-patch 机制

## 当前状态

- 集成代码: **已就绪**
- 默认版本: **v1**（生产安全）
- 切换条件: 人工复核通过 → ADOPT_V2 → 修改环境变量为 v2
- 灰度方案: 见 `PROMPT_V2_ROLLOUT_PLAN.md`
