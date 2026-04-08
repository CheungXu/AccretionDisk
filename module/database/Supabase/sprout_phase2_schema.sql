-- Sprout 二期数据库结构
-- 说明：
-- 1. 该文件用于初始化数据库结构，不直接包含所有 RLS policy。
-- 2. RLS 与 Storage policy 见 sprout_phase2_rls.sql。

create extension if not exists pgcrypto;

create table if not exists public.profiles (
    id uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    avatar_url text,
    email text,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.projects (
    project_id text primary key,
    project_type text not null default 'sprout',
    display_name text not null,
    project_name text not null,
    title text,
    topic text,
    status text not null default 'draft',
    schema_version text not null default 'v1',
    import_mode text not null default 'reference',
    health_status text not null default 'ready',
    cover_asset_id text,
    current_manifest_snapshot_id text,
    created_by uuid references auth.users (id) on delete set null,
    imported_at timestamptz not null default timezone('utc', now()),
    last_active_at timestamptz not null default timezone('utc', now()),
    metadata jsonb not null default '{}'::jsonb,
    active_state jsonb not null default '{}'::jsonb
);

create table if not exists public.project_members (
    project_id text not null references public.projects (project_id) on delete cascade,
    user_id uuid not null references auth.users (id) on delete cascade,
    role text not null check (role in ('owner', 'editor', 'viewer')),
    invited_by uuid references auth.users (id) on delete set null,
    joined_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now()),
    status text not null default 'active',
    primary key (project_id, user_id)
);

create table if not exists public.project_assets (
    asset_id text primary key,
    project_id text not null references public.projects (project_id) on delete cascade,
    asset_type text not null,
    source text not null,
    bucket_name text not null,
    object_path text not null,
    public_url text,
    role text,
    prompt text,
    owner_user_id uuid references auth.users (id) on delete set null,
    shot_id text,
    character_id text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default timezone('utc', now()),
    unique (project_id, object_path)
);

create table if not exists public.project_snapshots (
    snapshot_id text primary key,
    project_id text not null references public.projects (project_id) on delete cascade,
    snapshot_type text not null check (snapshot_type in ('bundle', 'manifest', 'node_version', 'export')),
    bucket_name text not null,
    object_path text not null,
    content_sha256 text,
    source_version_id text,
    created_by uuid references auth.users (id) on delete set null,
    created_at timestamptz not null default timezone('utc', now()),
    metadata jsonb not null default '{}'::jsonb,
    unique (project_id, object_path)
);

create table if not exists public.project_versions (
    version_id text primary key,
    project_id text not null references public.projects (project_id) on delete cascade,
    node_type text not null,
    node_key text not null,
    snapshot_id text references public.project_snapshots (snapshot_id) on delete set null,
    source_version_id text,
    status text not null default 'ready',
    run_id text,
    asset_ids jsonb not null default '[]'::jsonb,
    shot_ids jsonb not null default '[]'::jsonb,
    dependency_version_ids jsonb not null default '{}'::jsonb,
    notes jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.project_runs (
    run_id text primary key,
    project_id text not null references public.projects (project_id) on delete cascade,
    node_type text not null,
    node_key text not null,
    log_bucket_name text,
    log_object_path text,
    status text not null default 'running',
    source_version_id text,
    result_version_id text,
    shot_ids jsonb not null default '[]'::jsonb,
    error_message text,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);

create index if not exists idx_projects_created_by on public.projects (created_by);
create index if not exists idx_project_members_user_id on public.project_members (user_id);
create index if not exists idx_project_assets_project_id on public.project_assets (project_id);
create index if not exists idx_project_snapshots_project_id on public.project_snapshots (project_id);
create index if not exists idx_project_versions_project_id on public.project_versions (project_id);
create index if not exists idx_project_runs_project_id on public.project_runs (project_id);

insert into storage.buckets (id, name, public)
values ('sprout-projects', 'sprout-projects', false)
on conflict (id) do nothing;
