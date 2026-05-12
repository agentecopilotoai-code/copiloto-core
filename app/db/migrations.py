"""Idempotent runtime migrations.

This module applies forward-only DDL that may be missing from databases
initialised before the schema in `infra/postgres/01-schema.sql` was extended.
Each block uses `if not exists` / `do $$ ... $$` so it is safe to run on every
startup. Keep statements small and isolated so a partially-applied database
converges.
"""
from __future__ import annotations

import structlog

import asyncpg

log = structlog.get_logger()


CRM_CONTACT_FEATURES_SQL = """
create table if not exists app.contact_tags (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  color varchar(7),
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name)
);
create index if not exists ix_contact_tags_tenant on app.contact_tags(tenant_id, name);

create table if not exists app.contact_tag_assignments (
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  tag_id uuid not null references app.contact_tags(id) on delete cascade,
  assigned_by uuid references app.users(id) on delete set null,
  assigned_at timestamptz not null default now(),
  primary key (contact_id, tag_id)
);
create index if not exists ix_contact_tag_assignments_tag on app.contact_tag_assignments(tag_id);
create index if not exists ix_contact_tag_assignments_tenant on app.contact_tag_assignments(tenant_id);

create table if not exists app.contact_notes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  body text not null,
  created_by uuid references app.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists ix_contact_notes_contact on app.contact_notes(tenant_id, contact_id, created_at desc);

do $$
begin
  if not exists (
    select 1 from pg_constraint where conname = 'uq_contact_tags_tenant_id_id'
  ) then
    alter table app.contact_tags add constraint uq_contact_tags_tenant_id_id unique (tenant_id, id);
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'uq_contact_notes_tenant_id_id'
  ) then
    alter table app.contact_notes add constraint uq_contact_notes_tenant_id_id unique (tenant_id, id);
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'fk_contact_tag_assignments_tenant_contact'
  ) then
    alter table app.contact_tag_assignments
      add constraint fk_contact_tag_assignments_tenant_contact
      foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id);
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'fk_contact_tag_assignments_tenant_tag'
  ) then
    alter table app.contact_tag_assignments
      add constraint fk_contact_tag_assignments_tenant_tag
      foreign key (tenant_id, tag_id) references app.contact_tags(tenant_id, id);
  end if;
  if not exists (
    select 1 from pg_constraint where conname = 'fk_contact_notes_tenant_contact'
  ) then
    alter table app.contact_notes
      add constraint fk_contact_notes_tenant_contact
      foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id);
  end if;
end $$;

do $$
begin
  if not exists (select 1 from pg_trigger where tgname = 'trg_contact_tags_touch') then
    create trigger trg_contact_tags_touch before update on app.contact_tags
      for each row execute function app.touch_updated_at();
  end if;
  if not exists (select 1 from pg_trigger where tgname = 'trg_contact_notes_touch') then
    create trigger trg_contact_notes_touch before update on app.contact_notes
      for each row execute function app.touch_updated_at();
  end if;
end $$;

alter table app.contact_tags enable row level security;
alter table app.contact_tag_assignments enable row level security;
alter table app.contact_notes enable row level security;

do $$
declare t text;
begin
  foreach t in array array['contact_tags','contact_tag_assignments','contact_notes'] loop
    if not exists (
      select 1 from pg_policies where schemaname='app' and tablename=t and policyname = t || '_tenant_select'
    ) then
      execute format('create policy %I_tenant_select on app.%I for select using (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname='app' and tablename=t and policyname = t || '_tenant_insert'
    ) then
      execute format('create policy %I_tenant_insert on app.%I for insert with check (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname='app' and tablename=t and policyname = t || '_tenant_update'
    ) then
      execute format('create policy %I_tenant_update on app.%I for update using (tenant_id = app.current_tenant_id() or app.support_mode()) with check (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    end if;
    if not exists (
      select 1 from pg_policies where schemaname='app' and tablename=t and policyname = t || '_tenant_delete'
    ) then
      execute format('create policy %I_tenant_delete on app.%I for delete using (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    end if;
  end loop;
end $$;
"""


async def run_runtime_migrations(pool: asyncpg.Pool) -> None:
    """Apply idempotent forward-only migrations.

    Called from the FastAPI lifespan after the pool is connected.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(CRM_CONTACT_FEATURES_SQL)
    log.info('db.migrations.applied', migration='crm_contact_features')
