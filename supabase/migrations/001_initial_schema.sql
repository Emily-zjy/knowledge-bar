create extension if not exists "pgcrypto";

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  nickname text,
  avatar_path text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.knowledge_bases (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  description text not null default '',
  color text not null default '#ff6d29',
  content_md text not null default '',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.tags (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  name text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, name)
);

create table if not exists public.knowledge_base_tags (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  tag_id uuid not null references public.tags(id) on delete cascade,
  selected_text text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (knowledge_base_id, tag_id, selected_text)
);

create table if not exists public.attachments (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  storage_path text not null,
  file_name text not null,
  mime_type text not null,
  file_size integer not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.mind_maps (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  data_jsonb jsonb not null,
  markdown text not null default '',
  version_no integer not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.ai_generation_jobs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles(id) on delete cascade,
  knowledge_base_id uuid not null references public.knowledge_bases(id) on delete cascade,
  status text not null check (status in ('pending', 'running', 'succeeded', 'failed')),
  error_code text,
  error_message text,
  model_name text,
  prompt_version text,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.knowledge_bases enable row level security;
alter table public.tags enable row level security;
alter table public.knowledge_base_tags enable row level security;
alter table public.attachments enable row level security;
alter table public.mind_maps enable row level security;
alter table public.ai_generation_jobs enable row level security;

drop policy if exists "profiles own select" on public.profiles;
create policy "profiles own select" on public.profiles for select using (auth.uid() = id);
drop policy if exists "profiles own update" on public.profiles;
create policy "profiles own update" on public.profiles for update using (auth.uid() = id);
drop policy if exists "profiles own insert" on public.profiles;
create policy "profiles own insert" on public.profiles for insert with check (auth.uid() = id);

drop policy if exists "knowledge_bases own all" on public.knowledge_bases;
create policy "knowledge_bases own all" on public.knowledge_bases for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "tags own all" on public.tags;
create policy "tags own all" on public.tags for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "knowledge_base_tags own all" on public.knowledge_base_tags;
create policy "knowledge_base_tags own all" on public.knowledge_base_tags for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "attachments own all" on public.attachments;
create policy "attachments own all" on public.attachments for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "mind_maps own all" on public.mind_maps;
create policy "mind_maps own all" on public.mind_maps for all using (auth.uid() = user_id) with check (auth.uid() = user_id);
drop policy if exists "ai_generation_jobs own all" on public.ai_generation_jobs;
create policy "ai_generation_jobs own all" on public.ai_generation_jobs for all using (auth.uid() = user_id) with check (auth.uid() = user_id);

create unique index if not exists mind_maps_one_latest_per_base
  on public.mind_maps(user_id, knowledge_base_id);

create unique index if not exists knowledge_base_tags_unique_selected_text
  on public.knowledge_base_tags(knowledge_base_id, tag_id, coalesce(selected_text, ''));

create index if not exists knowledge_bases_user_updated_idx
  on public.knowledge_bases(user_id, updated_at desc);

create index if not exists attachments_base_idx
  on public.attachments(knowledge_base_id);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at
before update on public.profiles
for each row execute function public.set_updated_at();

drop trigger if exists knowledge_bases_set_updated_at on public.knowledge_bases;
create trigger knowledge_bases_set_updated_at
before update on public.knowledge_bases
for each row execute function public.set_updated_at();

drop trigger if exists tags_set_updated_at on public.tags;
create trigger tags_set_updated_at
before update on public.tags
for each row execute function public.set_updated_at();

drop trigger if exists knowledge_base_tags_set_updated_at on public.knowledge_base_tags;
create trigger knowledge_base_tags_set_updated_at
before update on public.knowledge_base_tags
for each row execute function public.set_updated_at();

drop trigger if exists attachments_set_updated_at on public.attachments;
create trigger attachments_set_updated_at
before update on public.attachments
for each row execute function public.set_updated_at();

drop trigger if exists mind_maps_set_updated_at on public.mind_maps;
create trigger mind_maps_set_updated_at
before update on public.mind_maps
for each row execute function public.set_updated_at();

drop trigger if exists ai_generation_jobs_set_updated_at on public.ai_generation_jobs;
create trigger ai_generation_jobs_set_updated_at
before update on public.ai_generation_jobs
for each row execute function public.set_updated_at();

insert into storage.buckets (id, name, public)
values ('knowledge-bar-assets', 'knowledge-bar-assets', false)
on conflict (id) do nothing;

drop policy if exists "knowledge bar assets own select" on storage.objects;
create policy "knowledge bar assets own select"
on storage.objects for select
using (
  bucket_id = 'knowledge-bar-assets'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "knowledge bar assets own insert" on storage.objects;
create policy "knowledge bar assets own insert"
on storage.objects for insert
with check (
  bucket_id = 'knowledge-bar-assets'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "knowledge bar assets own update" on storage.objects;
create policy "knowledge bar assets own update"
on storage.objects for update
using (
  bucket_id = 'knowledge-bar-assets'
  and (storage.foldername(name))[1] = auth.uid()::text
)
with check (
  bucket_id = 'knowledge-bar-assets'
  and (storage.foldername(name))[1] = auth.uid()::text
);

drop policy if exists "knowledge bar assets own delete" on storage.objects;
create policy "knowledge bar assets own delete"
on storage.objects for delete
using (
  bucket_id = 'knowledge-bar-assets'
  and (storage.foldername(name))[1] = auth.uid()::text
);
