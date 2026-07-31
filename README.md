# Knowledge Bar

Knowledge Bar is a P0 AI knowledge base and mind map product.

## Stack

- Frontend: React + Vite + TypeScript
- Mind map: React Flow
- Backend: FastAPI
- Database/Auth/Storage: Supabase Auth + PostgreSQL + Storage
- Deploy: Vercel frontend, Railway backend

## Local Development

Start backend:

```bash
cd backend
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start frontend:

```bash
cd frontend
npm run dev
```

Open `http://localhost:5173`.

## Environment

Frontend uses only public variables. Copy `frontend/.env.example` to `frontend/.env.local` for local development:

```bash
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Backend keeps private keys:

```bash
AI_PROVIDER=mock
AI_API_KEY=
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
```

Do not put AI keys, database passwords, Supabase service role keys, or other private secrets in `VITE_*` variables.

## Current P0 Features

- 游客模式：IndexedDB 本地保存知识库和思维导图。
- 登录模式：配置 Supabase 后，邮箱注册/登录、知识库、标签、附件元数据和思维导图保存到云端。
- 图片：游客模式写入本地 Markdown 图片，登录模式上传到 Supabase Storage private bucket。
- AI 思维导图：FastAPI 封装 AI 调用，前端使用 React Flow 横向渲染。
- 导出：Markdown 前端导出，Word 由 FastAPI 生成，后端不可用时回退为 Word 兼容文件。

## Deployment

See `docs/deployment-checklist.md`.
