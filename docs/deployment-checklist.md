# Knowledge Bar P0 部署检查表

## Supabase

1. 创建 Supabase Project。
2. 在 SQL Editor 执行 `supabase/migrations/001_initial_schema.sql`。
3. 确认 `knowledge-bar-assets` bucket 已创建，且为 private。
4. 如果第一版不做邮箱验证，在 Auth 设置中关闭邮箱确认。
5. 复制 Project URL 和 anon key 给前端使用。

## Railway 后端

1. 新建 Railway Project，部署目录选择 `backend`。
2. 配置环境变量，参考 `backend/.env.example`。
3. `AI_API_KEY`、`AI_API_BASE_URL`、`AI_MODEL` 只放 Railway 后端。
4. 健康检查路径使用 `/health`。
5. 部署成功后记录后端域名，例如 `https://knowledge-bar-api.up.railway.app`。

## Vercel 前端

1. 新建 Vercel Project，Root Directory 选择 `frontend`。
2. Build Command 使用 `npm run build`。
3. Output Directory 使用 `dist`。
4. 配置环境变量，参考 `frontend/.env.example`。
5. `VITE_API_BASE_URL` 填 Railway 后端域名。
6. `VITE_SUPABASE_URL` 和 `VITE_SUPABASE_ANON_KEY` 可以放前端。

## CORS

Railway 后端的 `CORS_ORIGINS` 需要包含：

- 本地开发：`http://localhost:5173`
- 本地开发：`http://127.0.0.1:5173`
- Vercel 正式域名

## 上线前验收

- 邮箱注册、登录、退出可用。
- 游客模式可创建知识库并保存在本地。
- 登录用户可创建知识库并云端保存。
- 详情页可输入内容、添加标签、添加图片。
- 点击生成思维导图后能看到横向思维导图。
- 可导出 Markdown。
- 可导出 Word。
- AI 失败时前端显示失败原因，可重新点击生成。
