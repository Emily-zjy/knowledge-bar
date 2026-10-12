# Knowledge Bar

AI-powered knowledge organization tool for students and learners. Users create knowledge bases, input study materials, and generate structured mind maps with one click.

## Core Problem

Students and exam-prep users scatter notes across docs, screenshots, and chat logs. Reviewing becomes painful because there's no structure. Knowledge Bar solves this: paste your content, let AI organize it into a visual mind map you can edit, save, and export.

## V2 Updates

- Full-stack integration: FastAPI backend with JWT auth, Supabase storage, AI generation pipeline
- Real AI mind map generation (OpenAI-compatible or Anthropic) with structure validation
- Server-side job tracking for async generation
- Word/Markdown export from backend
- Secure auth: all AI/storage endpoints require Supabase JWT
- No fake fallback: AI failure shows real errors, not placeholder maps

## Features

| Feature | Description |
|---------|-------------|
| Knowledge Base CRUD | Create, edit, delete knowledge bases with rich markdown content |
| AI Mind Map Generation | Generate structured mind maps from content via LLM |
| Interactive Mind Map | View, edit nodes, drag layout (React Flow) |
| Cloud Save | Logged-in users get persistent storage via Supabase |
| Guest Mode | Try the editor without login (IndexedDB draft, no AI) |
| Word Export | Download .docx with title, content, and mind map structure |
| Markdown Export | Export knowledge base as .md |
| Image Attachments | Upload images to Supabase Storage, embed in content |
| Tags | Organize knowledge bases with tags |

## Architecture

```
┌─────────────┐       ┌──────────────────┐       ┌───────────────┐
│   Frontend  │──────▶│   FastAPI Backend │──────▶│  AI Provider  │
│  React/Vite │       │   (Python 3.11+) │       │ (OpenAI/Claude)│
└──────┬──────┘       └────────┬─────────┘       └───────────────┘
       │                       │
       │  Auth/CRUD            │  Service Role
       ▼                       ▼
┌──────────────────────────────────────────┐
│            Supabase                       │
│  Auth │ PostgreSQL │ Storage │ RLS        │
└──────────────────────────────────────────┘
```

**Frontend** (Vercel): UI, Supabase Auth, direct DB reads (RLS-protected), mind map rendering.

**Backend** (Railway): AI generation, JWT validation, structure validation, Word export, job tracking. Uses service_role for server-side DB writes to `mind_maps` and `generation_jobs`.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, React Flow, Motion |
| Styling | Custom CSS (no framework) |
| Backend | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| Database | Supabase PostgreSQL with RLS |
| Auth | Supabase Auth (JWT), backend verification via PyJWT |
| AI | OpenAI-compatible API or Anthropic Claude |
| Export | python-docx (Word), markdown generation |
| Deploy | Vercel (frontend), Railway (backend), Supabase (DB/Auth/Storage) |

## Directory Structure

```
knowledge-bar/
├── frontend/
│   ├── src/
│   │   ├── App.tsx              # Main app (auth, routing, KB management)
│   │   ├── pages/
│   │   │   └── MindMapPage.tsx  # Mind map view/edit page
│   │   ├── components/          # UI components (animations, effects)
│   │   ├── lib/
│   │   │   └── api.ts           # Backend API client
│   │   └── styles/              # CSS files
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, error handlers
│   │   ├── api/
│   │   │   ├── ai.py            # AI generation + export endpoints
│   │   │   └── mindmap.py       # Legacy mindmap CRUD endpoints
│   │   ├── core/
│   │   │   └── config.py        # Settings (env vars)
│   │   ├── models/
│   │   │   ├── ai.py            # Request/response models
│   │   │   └── mindmap.py       # Mindmap data models
│   │   └── services/
│   │       ├── ai_mindmap.py    # AI provider integration + validation
│   │       ├── auth.py          # JWT verification
│   │       └── supabase_store.py # Server-side Supabase operations
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
├── supabase/
│   └── migrations/              # Database schema migrations
├── docs/                        # PRD, API design, architecture docs
└── README.md
```

## Local Development

### Prerequisites

- Node.js 18+
- Python 3.11+
- Supabase project (free tier works)

### Frontend

```bash
cd frontend
npm install
npm run dev
# Runs at http://localhost:5173
```

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Environment Variables

Copy and fill:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
```

**Backend** (`backend/.env`):

| Variable | Required | Description |
|----------|----------|-------------|
| `AI_PROVIDER` | Yes | `openai`, `anthropic`, or `mock` |
| `AI_API_KEY` | Yes (unless mock) | API key for AI provider |
| `AI_BASE_URL` | No | Custom base URL for OpenAI-compatible APIs |
| `AI_MODEL` | No | Model name (default: provider-specific) |
| `AI_MAX_RETRIES` | No | Max retries on transient errors (default: 2) |
| `AI_MOCK_FALLBACK` | No | `true` to fallback to mock on AI failure (default: false) |
| `SUPABASE_URL` | Yes | Supabase project URL |
| `SUPABASE_ANON_KEY` | Yes | Supabase anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Yes | Supabase service role key (server only) |
| `SUPABASE_JWT_SECRET` | Yes | JWT secret for token verification |
| `APP_HOST` | No | Server host (default: 0.0.0.0) |
| `APP_PORT` | No | Server port (default: 8000) |

**Frontend** (`frontend/.env.local`):

| Variable | Required | Description |
|----------|----------|-------------|
| `VITE_SUPABASE_URL` | Yes | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Yes | Supabase anon key |
| `VITE_API_BASE_URL` | Yes | Backend API URL (e.g., `http://localhost:8000`) |

## Supabase Setup

### Database Tables

Core tables (managed via migrations in `supabase/migrations/`):

- `knowledge_bases` — user content storage
- `mind_maps` — generated mind map data (unique per user+KB, versioned)
- `ai_generation_jobs` — async generation job tracking
- `tags`, `knowledge_base_tags` — tagging system
- `attachments` — image metadata

### Row Level Security (RLS)

All tables have RLS enabled. Users can only access their own data. The backend uses `service_role` key to bypass RLS for server-side writes (mind map saves, job tracking).

### Storage

Supabase Storage bucket `attachments` for user-uploaded images. RLS policies restrict access to the owning user.

### Running Migrations

```bash
supabase db push
# Or apply individually:
supabase migration up
```

## AI Generation Pipeline

1. Frontend sends `POST /api/ai/mindmap/generate` with JWT + knowledge_base_id + content
2. Backend verifies JWT, confirms KB ownership via Supabase
3. Creates a `generation_job` record (status: running)
4. Calls AI provider (OpenAI-compatible or Anthropic) with structured prompt
5. Validates response: exactly 1 root, no duplicate IDs, valid parentIds, max 25 nodes, depth ≤ 6
6. On success: saves to `mind_maps`, updates job to `succeeded`
7. On failure: updates job to `failed` with error detail, returns error to client

Retries only on transient errors (timeout, network, 429, 5xx). Schema/validation errors fail immediately.

## Export

### Markdown

`GET /api/ai/export/markdown/{knowledge_base_id}` — returns markdown text of the knowledge base content and mind map structure.

### Word

`GET /api/ai/export/word/{knowledge_base_id}` — returns `.docx` file with formatted title, content paragraphs, and mind map outline.

`POST /api/ai/export/word` (legacy) — accepts `{title, nodes}` body directly, no auth required. For backward compatibility with existing frontend export.

## Testing

### Backend

```bash
cd backend
python -m pytest tests/ -q
```

### Frontend

```bash
cd frontend
npm run lint        # ESLint
npm run build       # TypeScript check + production build
```

## Deployment

### Frontend (Vercel)

1. Connect GitHub repo to Vercel
2. Set root directory to `frontend`
3. Set environment variables (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`)
4. Deploy — Vite build runs automatically

### Backend (Railway)

1. Connect GitHub repo to Railway
2. Set root directory to `backend`
3. Set environment variables (all backend vars from table above)
4. Railway uses Dockerfile — reads `PORT` env var automatically
5. Health check: `GET /health` returns `{"status":"ok","service":"knowledge-bar-api"}`

## Security

- All AI/export endpoints require valid Supabase JWT
- `service_role` key never exposed to frontend
- RLS enforces per-user data isolation at database level
- Backend validates knowledge base ownership before AI generation
- No secrets in `.env.example` (empty placeholders only)
- `.env` files gitignored
- Request IDs for traceability (`X-Request-ID` header)
- Input validation via Pydantic models with length constraints

## Current Limitations

- No real-time collaboration (single-user only)
- Mind map limited to 25 nodes / depth 6 (LLM output constraint)
- No OCR or URL parsing (P0 scope)
- No mind map version history (saves latest only, with version_no increment)
- Guest users cannot generate AI mind maps (JWT required)
- Frontend bundle > 500KB (React Flow + Motion); code splitting planned

## Roadmap

- [ ] OCR image-to-text for uploaded attachments
- [ ] URL/webpage content extraction
- [ ] AI chat assistant for Q&A over knowledge base
- [ ] Multi-version mind map history
- [ ] Team/shared knowledge bases
- [ ] Mobile-responsive layout improvements
- [ ] Code splitting for smaller initial bundle
