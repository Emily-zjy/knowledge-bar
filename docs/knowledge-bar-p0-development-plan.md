# Knowledge Bar P0 开发任务拆解文档

## 1. 开发目标

P0 开发目标是完成一个可真实上线的 Knowledge Bar 最小闭环：

> 登录 / 游客体验 -> 创建知识库 -> 编辑内容 -> 添加图片 / 标签 -> AI 生成思维导图 -> 保存最新版 -> 导出 Markdown / Word

P0 不追求一次性完成所有后续功能，优先保证主流程可用、数据归属清晰、AI 生成可演示、部署链路完整。

## 2. 工程结构

| 目录 | 说明 |
| --- | --- |
| `frontend` | React + Vite + TypeScript 前端 |
| `backend` | Python + FastAPI 后端 |
| `supabase` | 数据库表结构、RLS、Storage policy SQL |
| `docs` | PRD、技术架构、接口设计、开发计划 |
| `assets` | 原型和 UI 所需图片资源 |

## 3. 任务线总览

| 任务线 | 负责人角色 | P0 产出 |
| --- | --- | --- |
| 前端 | Frontend | 页面路由、登录注册、工作台、编辑器、思维导图、导出入口 |
| 后端 | Backend | FastAPI、AI 生成接口、Word 导出、健康检查、JWT 校验 |
| Supabase | Backend / Fullstack | Auth 配置、数据库表、RLS、Storage Bucket |
| AI | Backend / AI | Prompt、返回 JSON Schema、结构校验、失败重试 |
| 部署 | Fullstack | Vercel 前端、Railway 后端、Supabase 云服务 |

## 4. 里程碑

| 阶段 | 目标 | 验收标准 |
| --- | --- | --- |
| M1 工程骨架 | 建立前后端项目和 Supabase SQL | 前端、后端可本地启动；SQL 文件可执行 |
| M2 账号与工作台 | 接入 Supabase Auth 和知识库列表 | 用户可注册、登录、退出、看到自己的知识库 |
| M3 知识库编辑 | 创建、编辑、保存知识库内容 | 用户可创建知识库并保存正文 |
| M4 游客模式 | IndexedDB 保存游客草稿 | 游客可体验主流程，登录后提示同步 |
| M5 图片与标签 | 图片上传、标签添加和筛选展示 | 图片进入 Storage，标签进入数据库 |
| M6 AI 思维导图 | FastAPI 生成思维导图 JSON 并渲染 | 有内容时可生成，失败可重试 |
| M7 导出与部署 | Markdown / Word 导出，上线访问 | 前端 Vercel、后端 Railway、数据库 Supabase |

## 5. 前端任务拆解

| 编号 | 任务 | 优先级 |
| --- | --- | --- |
| FE-01 | 初始化 React + Vite + TypeScript | P0 |
| FE-02 | 配置 React Router 页面路由 | P0 |
| FE-03 | 搭建全局布局和 Knowledge Bar 主题样式 | P0 |
| FE-04 | 登录页：登录、注册入口、跳过体验 | P0 |
| FE-05 | 注册页：邮箱密码注册 | P0 |
| FE-06 | 我的 knowledge bar：列表、搜索、空状态、新建入口 | P0 |
| FE-07 | 创建 knowledge bar 表单 | P0 |
| FE-08 | 详情编辑页：自由文档编辑、保存、工具栏 | P0 |
| FE-09 | 添加标签交互：选中文字、创建标签、展示标签 | P0 |
| FE-10 | 添加图片入口：文件校验、上传、插入编辑区 | P0 |
| FE-11 | 思维导图页：React Flow 渲染、节点编辑 | P0 |
| FE-12 | 导出 MD / Word 入口 | P0 |
| FE-13 | Loading、Toast、失败重试、防重复提交 | P0 |
| FE-14 | IndexedDB 游客草稿 | P0 |

## 6. 后端任务拆解

| 编号 | 任务 | 优先级 |
| --- | --- | --- |
| BE-01 | 初始化 FastAPI 项目 | P0 |
| BE-02 | `/health` 健康检查 | P0 |
| BE-03 | CORS 配置 | P0 |
| BE-04 | Supabase JWT 校验工具 | P0 |
| BE-05 | AI Provider Adapter | P0 |
| BE-06 | 思维导图 Pydantic Schema | P0 |
| BE-07 | `/api/ai/mindmap/generate` | P0 |
| BE-08 | `ai_generation_jobs` 状态记录 | P0 |
| BE-09 | AI 失败错误码和重试响应 | P0 |
| BE-10 | `/api/export/word` | P0 |
| BE-11 | `/api/export/markdown` 可选接口 | P1 |
| BE-12 | 请求 ID、AI 耗时、错误日志 | P0 |

## 7. Supabase 任务拆解

| 编号 | 任务 | 优先级 |
| --- | --- | --- |
| DB-01 | 创建 Supabase 项目 | P0 |
| DB-02 | 配置邮箱密码 Auth | P0 |
| DB-03 | 建表：profiles、knowledge_bases、tags、knowledge_base_tags | P0 |
| DB-04 | 建表：attachments、mind_maps、ai_generation_jobs | P0 |
| DB-05 | 开启 RLS | P0 |
| DB-06 | 编写 user_id = auth.uid() 策略 | P0 |
| DB-07 | 创建私有 Storage Bucket | P0 |
| DB-08 | 配置 Storage 权限策略 | P0 |

## 8. AI 任务拆解

| 编号 | 任务 | 优先级 |
| --- | --- | --- |
| AI-01 | 确认 AI Provider 和模型名称 | P0 |
| AI-02 | 设计 Prompt v1 | P0 |
| AI-03 | 固定思维导图 JSON Schema | P0 |
| AI-04 | 生成结果结构校验 | P0 |
| AI-05 | 内容为空拦截 | P0 |
| AI-06 | 超时、失败、格式错误处理 | P0 |
| AI-07 | 记录 prompt_version 和 model_name | P0 |

## 9. 部署任务拆解

| 编号 | 任务 | 优先级 |
| --- | --- | --- |
| DEP-01 | Vercel 前端部署 | P0 |
| DEP-02 | Railway 后端部署 | P0 |
| DEP-03 | Railway Dockerfile | P0 |
| DEP-04 | 配置 Vercel 环境变量 | P0 |
| DEP-05 | 配置 Railway 环境变量 | P0 |
| DEP-06 | 配置 CORS 白名单 | P0 |
| DEP-07 | 配置 `/health` 健康检查 | P0 |

## 10. 当前开发顺序

1. 搭建前端和后端项目骨架。
2. 写 Supabase SQL 初版。
3. 实现无真实 Supabase 配置下可运行的前端静态主流程。
4. 实现 FastAPI mock AI 生成接口。
5. 接入真实 Supabase 环境变量。
6. 接入真实 AI Provider。
7. 上线部署。

