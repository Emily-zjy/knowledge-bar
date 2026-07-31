# Knowledge Bar P0 接口设计文档

## 1. 文档目标

本文档用于细化 Knowledge Bar P0 的前端数据调用、FastAPI 后端接口、AI 生成接口、导出接口、错误码和权限校验规则。

P0 接口设计遵循一个原则：

> 普通用户数据操作优先由前端通过 Supabase SDK 直连 Supabase，在 RLS 保护下完成；涉及 AI Key、service_role、Word 导出、结构校验和服务端日志的操作必须经过 FastAPI。

## 2. 调用边界总览

| 功能 | 调用方式 | 说明 |
| --- | --- | --- |
| 注册 | 前端 -> Supabase Auth | 邮箱密码注册 |
| 登录 | 前端 -> Supabase Auth | 邮箱密码登录 |
| 退出登录 | 前端 -> Supabase Auth | 清除用户会话 |
| 获取当前用户 | 前端 -> Supabase Auth | 判断登录状态 |
| 知识库列表 | 前端 -> Supabase PostgreSQL | RLS 限制只返回当前用户数据 |
| 创建知识库 | 前端 -> Supabase PostgreSQL | 写入 `knowledge_bases` |
| 更新知识库 | 前端 -> Supabase PostgreSQL | 更新 `knowledge_bases` |
| 删除知识库 | 前端 -> Supabase PostgreSQL | 删除知识库及关联数据 |
| 保存正文 | 前端 -> Supabase PostgreSQL | 更新 `knowledge_bases.content_md` |
| 标签管理 | 前端 -> Supabase PostgreSQL | 写入 `tags` 和 `knowledge_base_tags` |
| 图片上传 | 前端 -> Supabase Storage + PostgreSQL | 文件进入 Storage，元数据进入 `attachments` |
| 游客草稿 | 前端 -> IndexedDB | 不写入 Supabase |
| AI 生成思维导图 | 前端 -> FastAPI -> AI | 后端校验 JWT、调用 AI、校验结构、保存结果 |
| Word 导出 | 前端 -> FastAPI | 后端生成 `.docx` |
| Markdown 导出 | 前端或 FastAPI | P0 建议前端生成，后续可统一后端 |

## 3. Supabase 前端调用清单

### 3.1 Auth

#### 3.1.1 注册

| 项目 | 说明 |
| --- | --- |
| 方法 | `supabase.auth.signUp` |
| 输入 | `email`、`password` |
| 成功 | 创建用户账号，进入登录态或等待 Supabase 返回会话 |
| 失败 | 邮箱已注册、邮箱格式错误、密码不符合规则、网络失败 |
| 页面反馈 | 注册中 Loading；失败展示错误原因 |

#### 3.1.2 登录

| 项目 | 说明 |
| --- | --- |
| 方法 | `supabase.auth.signInWithPassword` |
| 输入 | `email`、`password` |
| 成功 | 获得用户会话，进入“我的 knowledge bar” |
| 失败 | 账号不存在、密码错误、网络失败 |
| 页面反馈 | 登录中 Loading；失败展示错误原因 |

#### 3.1.3 退出登录

| 项目 | 说明 |
| --- | --- |
| 方法 | `supabase.auth.signOut` |
| 成功 | 清除会话，返回登录页 |
| 游客草稿 | 退出登录不删除 IndexedDB 游客草稿 |

### 3.2 knowledge_bases

#### 3.2.1 获取知识库列表

| 项目 | 说明 |
| --- | --- |
| 表 | `knowledge_bases` |
| 操作 | `select` |
| 查询条件 | 当前登录用户由 RLS 自动限制；前端可追加搜索条件 |
| 排序 | `updated_at desc` |
| 返回字段 | `id`、`name`、`description`、`color`、`content_md`、`created_at`、`updated_at` |
| 空状态 | 返回空数组时展示创建引导 |

#### 3.2.2 创建知识库

| 项目 | 说明 |
| --- | --- |
| 表 | `knowledge_bases` |
| 操作 | `insert` |
| 必填 | `user_id`、`name` |
| 可选 | `description`、`color`、`content_md` |
| 成功 | 返回新知识库 ID，并跳转详情页 |
| 失败 | 名称为空、无权限、网络失败 |

#### 3.2.3 更新知识库

| 项目 | 说明 |
| --- | --- |
| 表 | `knowledge_bases` |
| 操作 | `update` |
| 可更新字段 | `name`、`description`、`color`、`content_md`、`updated_at` |
| 权限 | RLS 限制只能更新自己的知识库 |
| 成功 | 刷新页面展示 |
| 失败 | 无权限、保存失败、网络失败 |

#### 3.2.4 删除知识库

| 项目 | 说明 |
| --- | --- |
| 表 | `knowledge_bases` |
| 操作 | `delete` |
| 前置 | 用户二次确认 |
| 关联数据 | `attachments`、`mind_maps`、`ai_generation_jobs`、`knowledge_base_tags` 需要一并处理 |
| 成功 | 返回“我的 knowledge bar” |
| 失败 | 无权限、删除失败、网络失败 |

### 3.3 tags 与 knowledge_base_tags

| 操作 | 说明 |
| --- | --- |
| 创建标签 | 向 `tags` 写入当前用户标签 |
| 关联知识库 | 向 `knowledge_base_tags` 写入 `knowledge_base_id` 和 `tag_id` |
| 选中文字 | `selected_text` 保存用户添加标签时选中的文本，可为空 |
| 标签展示 | 通过 `knowledge_base_tags` 查询当前知识库标签 |
| 权限 | 所有表通过 `user_id = auth.uid()` 受 RLS 保护 |

### 3.4 attachments 与 Storage

#### 3.4.1 图片上传

| 项目 | 说明 |
| --- | --- |
| 文件位置 | Supabase Storage 私有 Bucket |
| 元数据表 | `attachments` |
| 支持格式 | `png`、`jpg`、`jpeg`、`webp` |
| 大小限制 | 单张建议不超过 5MB |
| Storage 路径建议 | `{user_id}/{knowledge_base_id}/{attachment_id}-{file_name}` |
| 成功 | 上传文件后写入 `attachments` 元数据，再插入编辑器 |
| 失败 | 格式不支持、文件过大、上传失败、元数据写入失败 |

#### 3.4.2 attachments 写入字段

```json
{
  "id": "uuid",
  "user_id": "uuid",
  "knowledge_base_id": "uuid",
  "storage_path": "user/kb/file.png",
  "file_name": "file.png",
  "mime_type": "image/png",
  "file_size": 102400
}
```

## 4. 游客 IndexedDB 数据设计

游客模式不写入 Supabase，P0 使用 IndexedDB 保存临时数据。

### 4.1 IndexedDB stores

| Store | 作用 |
| --- | --- |
| `guest_knowledge_bases` | 保存游客知识库草稿 |
| `guest_attachments` | 保存游客图片引用或 Blob |
| `guest_mind_maps` | 保存游客生成的思维导图 |

### 4.2 guest_knowledge_bases 示例

```json
{
  "local_draft_id": "local-uuid",
  "name": "考研政治",
  "description": "强化阶段复习",
  "color": "orange",
  "content_md": "# 第一章 ...",
  "synced": false,
  "created_at": "2026-07-29T12:00:00.000Z",
  "updated_at": "2026-07-29T12:00:00.000Z"
}
```

### 4.3 游客同步规则

| 场景 | 规则 |
| --- | --- |
| 用户登录 / 注册成功 | 询问是否同步游客草稿 |
| 用户确认同步 | 创建云端知识库，写入正文、标签、图片、思维导图 |
| 同步成功 | 将本地草稿标记为 `synced = true`，可删除已同步草稿 |
| 同步失败 | 保留本地草稿，不得删除 |
| 重复同步 | 通过 `local_draft_id` 或 `synced` 防止重复 |

## 5. FastAPI 接口总览

FastAPI 接口统一使用 JSON 请求和 JSON 响应；导出接口返回文件流。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| POST | `/api/ai/mindmap/generate` | 生成思维导图 |
| POST | `/api/export/word` | 导出 Word |
| POST | `/api/export/markdown` | 导出 Markdown，可选 |

### 5.1 请求头

登录用户调用 FastAPI 时必须携带 Supabase JWT：

```text
Authorization: Bearer <supabase_jwt>
```

游客模式调用 AI 或导出时，P0 可使用临时 guest 标识，但不能访问云端用户数据。

```text
X-Guest-Session-Id: <local_guest_id>
```

### 5.2 通用成功响应

```json
{
  "success": true,
  "data": {}
}
```

### 5.3 通用失败响应

```json
{
  "success": false,
  "error": {
    "code": "AI_TIMEOUT",
    "message": "AI 生成超时，请稍后重试。"
  }
}
```

## 6. `GET /health`

### 6.1 说明

用于 Railway 健康检查和本地开发确认后端服务是否可用。

### 6.2 响应

```json
{
  "status": "ok",
  "service": "knowledge-bar-api",
  "time": "2026-07-29T12:00:00.000Z"
}
```

## 7. `POST /api/ai/mindmap/generate`

### 7.1 说明

基于知识库正文内容生成结构化思维导图 JSON。

### 7.2 请求体

```json
{
  "knowledge_base_id": "uuid-or-local-id",
  "title": "考研政治",
  "description": "强化阶段复习",
  "content_md": "# 马克思主义基本原理\n..."
}
```

### 7.3 服务端处理流程

1. 读取 Authorization 或 Guest Session。
2. 校验用户身份或游客身份。
3. 校验 `content_md` 不为空。
4. 登录用户需校验该 `knowledge_base_id` 是否属于当前用户。
5. 创建 `ai_generation_jobs` 记录，状态为 `running`。
6. 整理输入内容，调用 AI 生成接口。
7. 使用 Pydantic 校验 AI 返回结构。
8. 生成成功后保存 `mind_maps` 最新结果。
9. 更新 `ai_generation_jobs.status = succeeded`。
10. 返回思维导图 JSON。
11. 失败时记录错误码和错误信息，允许前端重试。

### 7.4 成功响应

```json
{
  "success": true,
  "data": {
    "generation_id": "uuid",
    "mind_map": {
      "title": "考研政治",
      "nodes": [
        {
          "id": "node-1",
          "parentId": null,
          "text": "考研政治",
          "order": 1
        },
        {
          "id": "node-2",
          "parentId": "node-1",
          "text": "马克思主义基本原理",
          "order": 1
        }
      ]
    }
  }
}
```

### 7.5 失败响应

```json
{
  "success": false,
  "error": {
    "code": "AI_FORMAT_INVALID",
    "message": "AI 返回结构无效，请重试。"
  }
}
```

## 8. `POST /api/export/word`

### 8.1 说明

将知识库内容或思维导图结构导出为 Word 文件。

### 8.2 请求体

```json
{
  "knowledge_base_id": "uuid-or-local-id",
  "title": "考研政治",
  "content_md": "# 考研政治\n...",
  "mind_map": {
    "title": "考研政治",
    "nodes": []
  }
}
```

### 8.3 成功响应

返回 `.docx` 文件流。

```text
Content-Type: application/vnd.openxmlformats-officedocument.wordprocessingml.document
Content-Disposition: attachment; filename="考研政治-2026-07-29.docx"
```

### 8.4 失败情况

| 错误 | 说明 |
| --- | --- |
| `EXPORT_FAILED` | Word 文件生成失败 |
| `UNAUTHORIZED` | 用户未登录且缺少游客会话 |
| `FORBIDDEN` | 登录用户无权导出该知识库 |

## 9. `POST /api/export/markdown`

P0 可以由前端直接生成 Markdown 文件。如果为了统一导出逻辑，也可以走 FastAPI。

### 9.1 请求体

```json
{
  "title": "考研政治",
  "content_md": "# 考研政治\n...",
  "mind_map_markdown": "# 考研政治\n- 主题 A"
}
```

### 9.2 成功响应

返回 `.md` 文件流。

```text
Content-Type: text/markdown; charset=utf-8
Content-Disposition: attachment; filename="考研政治-2026-07-29.md"
```

## 10. 思维导图 JSON Schema

后端必须校验 AI 返回结构。P0 固定使用节点扁平结构，前端可根据 `parentId` 渲染树。

```json
{
  "title": "知识库名称",
  "nodes": [
    {
      "id": "node-1",
      "parentId": null,
      "text": "中心主题",
      "order": 1
    }
  ]
}
```

### 10.1 字段规则

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `title` | string | 必填，思维导图标题 |
| `nodes` | array | 必填，节点数组 |
| `nodes[].id` | string | 必填，节点唯一 ID |
| `nodes[].parentId` | string / null | 根节点为 null，子节点指向父节点 ID |
| `nodes[].text` | string | 必填，节点显示文本 |
| `nodes[].order` | integer | 必填，同级排序 |

### 10.2 校验规则

| 校验项 | 规则 |
| --- | --- |
| 根节点 | 必须存在且只能有一个 `parentId = null` 的根节点 |
| 节点文本 | 不能为空 |
| 节点 ID | 同一张图内不能重复 |
| 父节点 | 非根节点的 `parentId` 必须能找到对应节点 |
| 节点数量 | P0 建议限制最大节点数，避免前端渲染过慢 |

## 11. 错误码

| 错误码 | 说明 | 前端处理 |
| --- | --- | --- |
| `EMPTY_CONTENT` | 知识库内容为空 | 提示先输入内容 |
| `UNAUTHORIZED` | 未登录或 Token 无效 | 引导登录 |
| `FORBIDDEN` | 无权访问该资源 | 提示无权限 |
| `AI_TIMEOUT` | AI 生成超时 | 提示重试 |
| `AI_FORMAT_INVALID` | AI 返回结构无效 | 提示重试 |
| `AI_PROVIDER_ERROR` | AI 服务错误 | 提示稍后重试 |
| `EXPORT_FAILED` | 导出失败 | 提示重新导出 |
| `VALIDATION_ERROR` | 请求参数不合法 | 展示具体字段错误 |
| `INTERNAL_ERROR` | 服务端未知错误 | 提示稍后重试 |

## 12. 权限校验规则

| 场景 | 规则 |
| --- | --- |
| 前端直连 Supabase | 依赖 Supabase Auth + RLS |
| FastAPI 登录用户请求 | 必须验证 JWT |
| FastAPI 游客请求 | 只允许处理请求体中的本地内容，不允许访问云端数据 |
| AI 生成 | 登录用户需校验知识库归属；游客只基于请求体生成 |
| 导出 | 登录用户需校验知识库归属；游客只导出请求体内容 |
| service_role | 只能用于后端必要场景，不能传给前端 |

## 13. 前端 Loading 与防重复提交

| 操作 | Loading | 防重复 |
| --- | --- | --- |
| 登录 | 是 | 禁用登录按钮 |
| 注册 | 是 | 禁用注册按钮 |
| 创建知识库 | 是 | 禁用创建按钮 |
| 保存内容 | 是 | 可短暂禁用保存按钮 |
| 上传图片 | 是 | 上传中禁用重复选择同一文件 |
| 生成思维导图 | 是 | 生成中禁用生成按钮 |
| 导出 Word | 是 | 导出中禁用导出按钮 |
| 删除知识库 | 是 | 二次确认后禁用删除按钮 |

## 14. 待确认问题

| 问题 | 当前建议 | 状态 |
| --- | --- | --- |
| Markdown 导出是否走后端 | P0 前端生成即可 | 待确认 |
| 游客是否允许调用 AI | 允许，但后续可加次数限制 | 待确认 |
| AI 最大输入长度 | P0 开发时设置限制 | 待确认 |
| 思维导图最大节点数 | P0 建议限制 | 待确认 |
| Word 导出格式 | 先支持标题、段落、列表、思维导图 Markdown | 待确认 |

