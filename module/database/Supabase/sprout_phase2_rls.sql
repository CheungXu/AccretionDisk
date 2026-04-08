-- Sprout 二期 RLS 与 Storage policy

create or replace function public.is_project_member(target_project_id text)
returns boolean
language sql
stable
as $$
    select exists(
        select 1
        from public.project_members pm
        where pm.project_id = target_project_id
          and pm.user_id = auth.uid()
          and pm.status = 'active'
    );
$$;

create or replace function public.has_project_role(target_project_id text, allowed_roles text[])
returns boolean
language sql
stable
as $$
    select exists(
        select 1
        from public.project_members pm
        where pm.project_id = target_project_id
          and pm.user_id = auth.uid()
          and pm.status = 'active'
          and pm.role = any(allowed_roles)
    );
$$;

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.project_assets enable row level security;
alter table public.project_snapshots enable row level security;
alter table public.project_versions enable row level security;
alter table public.project_runs enable row level security;

grant select, insert, update on public.profiles to authenticated;
grant select, insert, update, delete on public.projects to authenticated;
grant select, insert, update, delete on public.project_members to authenticated;
grant select, insert, update, delete on public.project_assets to authenticated;
grant select, insert, update, delete on public.project_snapshots to authenticated;
grant select, insert, update, delete on public.project_versions to authenticated;
grant select, insert, update, delete on public.project_runs to authenticated;

grant all on public.profiles to service_role;
grant all on public.projects to service_role;
grant all on public.project_members to service_role;
grant all on public.project_assets to service_role;
grant all on public.project_snapshots to service_role;
grant all on public.project_versions to service_role;
grant all on public.project_runs to service_role;

drop policy if exists "profiles_select_self" on public.profiles;
create policy "profiles_select_self"
on public.profiles
for select
to authenticated
using (id = auth.uid());

drop policy if exists "profiles_insert_self" on public.profiles;
create policy "profiles_insert_self"
on public.profiles
for insert
to authenticated
with check (id = auth.uid());

drop policy if exists "profiles_update_self" on public.profiles;
create policy "profiles_update_self"
on public.profiles
for update
to authenticated
using (id = auth.uid())
with check (id = auth.uid());

drop policy if exists "projects_select_member" on public.projects;
create policy "projects_select_member"
on public.projects
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "projects_insert_creator" on public.projects;
create policy "projects_insert_creator"
on public.projects
for insert
to authenticated
with check (created_by = auth.uid());

drop policy if exists "projects_update_editor" on public.projects;
create policy "projects_update_editor"
on public.projects
for update
to authenticated
using (public.has_project_role(project_id, array['owner', 'editor']))
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "projects_delete_owner" on public.projects;
create policy "projects_delete_owner"
on public.projects
for delete
to authenticated
using (public.has_project_role(project_id, array['owner']));

drop policy if exists "project_members_select_member" on public.project_members;
create policy "project_members_select_member"
on public.project_members
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "project_members_mutate_owner" on public.project_members;
create policy "project_members_mutate_owner"
on public.project_members
for all
to authenticated
using (public.has_project_role(project_id, array['owner']))
with check (public.has_project_role(project_id, array['owner']));

drop policy if exists "project_assets_select_member" on public.project_assets;
create policy "project_assets_select_member"
on public.project_assets
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "project_assets_insert_editor" on public.project_assets;
create policy "project_assets_insert_editor"
on public.project_assets
for insert
to authenticated
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_assets_update_editor" on public.project_assets;
create policy "project_assets_update_editor"
on public.project_assets
for update
to authenticated
using (public.has_project_role(project_id, array['owner', 'editor']))
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_assets_delete_owner" on public.project_assets;
create policy "project_assets_delete_owner"
on public.project_assets
for delete
to authenticated
using (public.has_project_role(project_id, array['owner']));

drop policy if exists "project_snapshots_select_member" on public.project_snapshots;
create policy "project_snapshots_select_member"
on public.project_snapshots
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "project_snapshots_insert_editor" on public.project_snapshots;
create policy "project_snapshots_insert_editor"
on public.project_snapshots
for insert
to authenticated
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_snapshots_update_editor" on public.project_snapshots;
create policy "project_snapshots_update_editor"
on public.project_snapshots
for update
to authenticated
using (public.has_project_role(project_id, array['owner', 'editor']))
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_snapshots_delete_owner" on public.project_snapshots;
create policy "project_snapshots_delete_owner"
on public.project_snapshots
for delete
to authenticated
using (public.has_project_role(project_id, array['owner']));

drop policy if exists "project_versions_select_member" on public.project_versions;
create policy "project_versions_select_member"
on public.project_versions
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "project_versions_insert_editor" on public.project_versions;
create policy "project_versions_insert_editor"
on public.project_versions
for insert
to authenticated
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_versions_update_owner" on public.project_versions;
create policy "project_versions_update_owner"
on public.project_versions
for update
to authenticated
using (public.has_project_role(project_id, array['owner']))
with check (public.has_project_role(project_id, array['owner']));

drop policy if exists "project_runs_select_member" on public.project_runs;
create policy "project_runs_select_member"
on public.project_runs
for select
to authenticated
using (public.is_project_member(project_id));

drop policy if exists "project_runs_insert_editor" on public.project_runs;
create policy "project_runs_insert_editor"
on public.project_runs
for insert
to authenticated
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "project_runs_update_editor" on public.project_runs;
create policy "project_runs_update_editor"
on public.project_runs
for update
to authenticated
using (public.has_project_role(project_id, array['owner', 'editor']))
with check (public.has_project_role(project_id, array['owner', 'editor']));

drop policy if exists "storage_select_project_member" on storage.objects;
create policy "storage_select_project_member"
on storage.objects
for select
to authenticated
using (
    bucket_id = 'sprout-projects'
    and split_part(name, '/', 1) = 'projects'
    and public.is_project_member(split_part(name, '/', 2))
);

drop policy if exists "storage_insert_project_editor" on storage.objects;
create policy "storage_insert_project_editor"
on storage.objects
for insert
to authenticated
with check (
    bucket_id = 'sprout-projects'
    and split_part(name, '/', 1) = 'projects'
    and public.has_project_role(split_part(name, '/', 2), array['owner', 'editor'])
);

drop policy if exists "storage_update_project_editor" on storage.objects;
create policy "storage_update_project_editor"
on storage.objects
for update
to authenticated
using (
    bucket_id = 'sprout-projects'
    and split_part(name, '/', 1) = 'projects'
    and public.has_project_role(split_part(name, '/', 2), array['owner', 'editor'])
)
with check (
    bucket_id = 'sprout-projects'
    and split_part(name, '/', 1) = 'projects'
    and public.has_project_role(split_part(name, '/', 2), array['owner', 'editor'])
);

drop policy if exists "storage_delete_project_owner" on storage.objects;
create policy "storage_delete_project_owner"
on storage.objects
for delete
to authenticated
using (
    bucket_id = 'sprout-projects'
    and split_part(name, '/', 1) = 'projects'
    and public.has_project_role(split_part(name, '/', 2), array['owner'])
);
