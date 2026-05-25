-- =============================================================================
-- Módulo Gestión Documental (GD) — Schema SQL
-- =============================================================================
-- Cubre las épicas EP-019 (auditoría transversal), EP-001 (identidad/permisos),
-- y los stubs mínimos para EP-002 que el bloque 1 necesita.
--
-- Tareas cubiertas en este archivo (bloque 1 — 2026-05-23):
--   - GD-API-0115: DDL core.evento_auditoria
--   - GD-API-0116: Trigger append-only sobre core.evento_auditoria
--   - GD-API-0117: Helper SQL `core.emit_evento_auditoria()` (Python wrapper en app/gd/services/)
--   - GD-API-0118: View `core.evento_auditoria_unificada` (compatibilidad con app.audit_logs)
--                  ⚠️ NO destructivo. Ver PROGRESO_IMPLEMENTACION.md D1.
--   - GD-API-0001: Schema gd.* identidad/permisos (gd.rol, gd.permiso, gd.rol_permiso,
--                  gd.perfil_usuario, gd.asignacion_alcance, gd.cargo)
--
-- Carga: este archivo se ejecuta DESPUÉS de 01-schema.sql, 02-seed.sql, 03-migrations.sql.
-- Idempotente: todas las operaciones usan `create ... if not exists` o `create or replace`.
--
-- Convenciones respetadas del repo (de 01-schema.sql):
--   - snake_case
--   - app.current_tenant_id() para RLS (ya definida en 01-schema.sql)
--   - app.support_mode() para bypass de soporte (ya definida)
--   - app.touch_updated_at() para triggers updated_at (ya definida)
--   - gen_random_uuid() para PKs (pgcrypto ya cargada)
--   - timestamptz not null default now() para timestamps
-- =============================================================================

-- =============================================================================
-- 0. Extensiones requeridas
-- =============================================================================
-- pg_trgm — necesario para los índices GIN con `gin_trgm_ops` (búsqueda
-- por similaridad / trigram). Sin esto, el init falla en línea ~2676
-- con "operator class gin_trgm_ops does not exist", y todo lo que viene
-- después (incluidos los GRANTs del § 24) NO se aplica.
create extension if not exists pg_trgm;

-- =============================================================================
-- 1. Schema `core` — infraestructura transversal compartida
-- =============================================================================
create schema if not exists core;

-- GRANTs para que `copiloto_app` (rol de la API) pueda leer/escribir las
-- tablas core (`core.evento_auditoria`, etc.). Sin esto, los handlers
-- que registran auditoría fallan con `permission denied for schema core`.
grant usage on schema core to copiloto_app;
grant select, insert, update, delete on all tables in schema core to copiloto_app;
grant usage, select on all sequences in schema core to copiloto_app;
alter default privileges in schema core
  grant select, insert, update, delete on tables to copiloto_app;
alter default privileges in schema core
  grant usage, select on sequences to copiloto_app;

-- 1.1 — GD-API-0115: core.evento_auditoria
-- Tabla append-only de eventos auditables del sistema completo (no solo GD).
-- Reemplaza CONCEPTUALMENTE a app.audit_logs + app.consent_ledger, pero NO las
-- borra ni renombra (ver D1 en PROGRESO_IMPLEMENTACION.md).
-- El campo `dominio` permite distinguir origen: core | app | gd | knowledge.
-- ----------------------------------------------------------------------------
create table if not exists core.evento_auditoria (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references app.tenants(id) on delete restrict,
  dominio text not null check (dominio in ('core', 'app', 'gd', 'knowledge')),
  tipo_evento text not null,
  criticidad text not null default 'media' check (criticidad in ('baja', 'media', 'alta', 'critica')),
  -- Actor (snapshot al momento del evento)
  usuario_id uuid references app.users(id) on delete restrict,
  actor_snapshot jsonb not null default '{}'::jsonb,  -- {nombre_completo, rol_codigo, dependencia_codigo, cargo}
  -- Entidad afectada (polimórfica)
  entidad_afectada_tipo text,
  entidad_afectada_id uuid,
  entidad_afectada_identificador text,  -- "RAD-2026-001234", "PERM-PQRSD-009", etc.
  -- Detalles
  accion text not null,
  valor_anterior jsonb,
  valor_nuevo jsonb,
  justificacion text,
  detalles jsonb not null default '{}'::jsonb,
  -- Request metadata
  request_id text,
  ip inet,
  user_agent text,
  -- Cuándo
  fecha_hora timestamptz not null default now()
);

comment on table core.evento_auditoria is
  'Eventos auditables transversales (EP-019). Append-only por trigger. '
  'Convive con app.audit_logs y app.consent_ledger por compatibilidad (ver PROGRESO_IMPLEMENTACION.md D1).';

comment on column core.evento_auditoria.dominio is
  'Origen del evento: core (infraestructura), app (producto principal), gd (gestión documental), knowledge (RAG).';

comment on column core.evento_auditoria.actor_snapshot is
  'Snapshot inmutable del usuario al momento del evento (RNF-006). '
  'Estructura sugerida: {usuario_id, nombre_completo, rol_codigo, rol_nombre, dependencia_codigo, dependencia_nombre, cargo, capturado_en}.';

-- Índices para queries típicos
create index if not exists ix_core_evento_auditoria_tenant_time
  on core.evento_auditoria(tenant_id, fecha_hora desc);

create index if not exists ix_core_evento_auditoria_entidad
  on core.evento_auditoria(entidad_afectada_tipo, entidad_afectada_id, fecha_hora desc)
  where entidad_afectada_tipo is not null;

create index if not exists ix_core_evento_auditoria_usuario
  on core.evento_auditoria(usuario_id, fecha_hora desc)
  where usuario_id is not null;

create index if not exists ix_core_evento_auditoria_tipo
  on core.evento_auditoria(tipo_evento, fecha_hora desc);

create index if not exists ix_core_evento_auditoria_dominio_criticidad
  on core.evento_auditoria(dominio, criticidad, fecha_hora desc);

-- ----------------------------------------------------------------------------
-- 1.2 — GD-API-0116: Trigger append-only
-- Bloquea UPDATE y DELETE sobre core.evento_auditoria (Mandato #6 del README GD).
-- ----------------------------------------------------------------------------
create or replace function core.evento_auditoria_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'core.evento_auditoria es append-only — UPDATE/DELETE no permitido'
    using errcode = '42501';  -- insufficient_privilege
end;
$$;

drop trigger if exists trg_core_evento_auditoria_no_update on core.evento_auditoria;
create trigger trg_core_evento_auditoria_no_update
  before update on core.evento_auditoria
  for each row execute function core.evento_auditoria_block_mutations();

drop trigger if exists trg_core_evento_auditoria_no_delete on core.evento_auditoria;
create trigger trg_core_evento_auditoria_no_delete
  before delete on core.evento_auditoria
  for each row execute function core.evento_auditoria_block_mutations();

-- RLS: tenant-scoped (un tenant solo ve sus propios eventos, support_mode bypass).
alter table core.evento_auditoria enable row level security;

drop policy if exists evento_auditoria_tenant_isolation on core.evento_auditoria;
create policy evento_auditoria_tenant_isolation on core.evento_auditoria
  for all
  using (
    tenant_id is null  -- eventos globales (sin tenant) visibles para todos
    or tenant_id = app.current_tenant_id()
    or app.support_mode()
  )
  with check (
    tenant_id is null
    or tenant_id = app.current_tenant_id()
    or app.support_mode()
  );

-- ----------------------------------------------------------------------------
-- 1.3 — GD-API-0117: Helper SQL `core.emit_evento_auditoria()`
-- Función SQL convenience para insertar eventos. El wrapper Python vive en
-- app/gd/services/audit_emitter.py y llama a esta función o hace insert directo.
-- ----------------------------------------------------------------------------
create or replace function core.emit_evento_auditoria(
  p_dominio text,
  p_tipo_evento text,
  p_accion text,
  p_tenant_id uuid default null,
  p_usuario_id uuid default null,
  p_actor_snapshot jsonb default '{}'::jsonb,
  p_entidad_afectada_tipo text default null,
  p_entidad_afectada_id uuid default null,
  p_entidad_afectada_identificador text default null,
  p_valor_anterior jsonb default null,
  p_valor_nuevo jsonb default null,
  p_justificacion text default null,
  p_detalles jsonb default '{}'::jsonb,
  p_criticidad text default 'media',
  p_request_id text default null,
  p_ip inet default null,
  p_user_agent text default null
)
returns uuid language plpgsql security definer as $$
declare
  v_evento_id uuid;
begin
  insert into core.evento_auditoria (
    tenant_id, dominio, tipo_evento, criticidad,
    usuario_id, actor_snapshot,
    entidad_afectada_tipo, entidad_afectada_id, entidad_afectada_identificador,
    accion, valor_anterior, valor_nuevo, justificacion, detalles,
    request_id, ip, user_agent
  ) values (
    p_tenant_id, p_dominio, p_tipo_evento, p_criticidad,
    p_usuario_id, p_actor_snapshot,
    p_entidad_afectada_tipo, p_entidad_afectada_id, p_entidad_afectada_identificador,
    p_accion, p_valor_anterior, p_valor_nuevo, p_justificacion, p_detalles,
    p_request_id, p_ip, p_user_agent
  )
  returning id into v_evento_id;

  return v_evento_id;
end;
$$;

comment on function core.emit_evento_auditoria is
  'GD-API-0117: helper para insertar eventos en core.evento_auditoria. '
  'Usar SECURITY DEFINER porque algunos callers (workers) pueden no tener tenant_id seteado pero deben poder auditar.';

-- ----------------------------------------------------------------------------
-- 1.4 — GD-API-0118 (REINTERPRETADO — ver D1):
-- View de compatibilidad que UNION ALL app.audit_logs + core.evento_auditoria.
-- Permite que reports de auditoría legacy y nuevos vean ambos buckets sin
-- migración destructiva. Migración real (mover datos) queda para fase 2.
--
-- NOTE: la view es read-only por defecto. Inserts deben ir directamente a
-- core.evento_auditoria (vía core.emit_evento_auditoria) o a app.audit_logs
-- (vía app/services/audit.py existente).
-- ----------------------------------------------------------------------------
-- Mapeo real (verificado contra app.audit_logs línea 898 de 01-schema.sql):
--   app.audit_logs.id          bigserial  → expuesto como text 'app:<id>'
--   app.audit_logs.actor_type  text       → desambiguar para usuario_id
--   app.audit_logs.actor_id    text       → solo UUID si actor_type='user'
--   app.audit_logs.action      text       → tipo_evento Y accion
--   app.audit_logs.entity_type/entity_id  → entidad_afectada_*
--   app.audit_logs.ip          inet       → ip
--   app.audit_logs.metadata    jsonb      → detalles
--   (NO existen actor_snapshot, before/after_state, justification, request_id)
create or replace view core.evento_auditoria_unificada as
  -- Eventos nuevos (post-EP-019)
  select
    'core:' || ce.id::text as id_unificado,
    ce.id as id_nuevo,
    null::bigint as id_legacy,
    ce.tenant_id,
    ce.dominio,
    ce.tipo_evento,
    ce.criticidad,
    ce.usuario_id,
    ce.actor_snapshot,
    ce.entidad_afectada_tipo,
    ce.entidad_afectada_id::text as entidad_afectada_id_text,
    ce.entidad_afectada_identificador,
    ce.accion,
    ce.valor_anterior,
    ce.valor_nuevo,
    ce.justificacion,
    ce.detalles,
    ce.request_id,
    ce.ip,
    ce.user_agent,
    ce.fecha_hora,
    'core.evento_auditoria'::text as origen_tabla
  from core.evento_auditoria ce

  union all

  -- Eventos legacy (pre-EP-019) desde app.audit_logs.
  select
    'app:' || al.id::text as id_unificado,
    null::uuid as id_nuevo,
    al.id as id_legacy,
    al.tenant_id,
    'app'::text as dominio,
    al.action as tipo_evento,
    'media'::text as criticidad,
    -- actor_id solo es UUID si actor_type='user'; en otros casos (bot, service, anonymous) → NULL
    case
      when al.actor_type = 'user' and al.actor_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
        then al.actor_id::uuid
      else null
    end as usuario_id,
    jsonb_build_object('actor_type', al.actor_type, 'actor_id', al.actor_id) as actor_snapshot,
    al.entity_type as entidad_afectada_tipo,
    null::text as entidad_afectada_id_text,  -- app.audit_logs.entity_id es text libre, no necesariamente UUID
    al.entity_id as entidad_afectada_identificador,
    al.action as accion,
    null::jsonb as valor_anterior,
    null::jsonb as valor_nuevo,
    null::text as justificacion,
    coalesce(al.metadata, '{}'::jsonb) as detalles,
    null::text as request_id,
    al.ip,
    al.user_agent,
    al.created_at as fecha_hora,
    'app.audit_logs'::text as origen_tabla
  from app.audit_logs al;

comment on view core.evento_auditoria_unificada is
  'GD-API-0118 (reinterpretado, ver PROGRESO_IMPLEMENTACION.md D1): '
  'view UNION ALL de core.evento_auditoria + app.audit_logs para reportes que '
  'necesiten ver ambos buckets sin migración destructiva. Read-only. '
  'Inserts deben ir a la tabla apropiada según dominio.';

-- =============================================================================
-- 2. Schema `gd` — Módulo Gestión Documental
-- =============================================================================
create schema if not exists gd;

-- ----------------------------------------------------------------------------
-- 2.1 — GD-API-0001: Catálogo de roles GD
-- Tabla global (sin RLS) — los 19 roles del PDF Matriz de Roles + custom por org.
-- ----------------------------------------------------------------------------
create table if not exists gd.rol (
  codigo text primary key,  -- ej. 'gd.radicador', 'gd.profesional'
  nombre text not null,
  descripcion text,
  es_sistema boolean not null default false,  -- true para los 19 roles seed
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table gd.rol is
  'GD-API-0001: catálogo de tipos de rol GD. Los 19 roles seed (es_sistema=true) '
  'vienen de la Matriz de Roles (PDF Doc 3). Roles custom (es_sistema=false) los '
  'puede crear cada organización vía POST /api/v1/gd/roles.';

-- Helper para prohibir DELETE si el rol tiene asignaciones activas se define
-- al final del archivo (depende de gd.asignacion_alcance) — sección 2.7.

-- ----------------------------------------------------------------------------
-- 2.2 — GD-API-0001: Catálogo de permisos GD
-- Tabla global (sin RLS) — ~140 permisos del PDF + PERM-PER-001..012 de EP-021.
-- ----------------------------------------------------------------------------
create table if not exists gd.permiso (
  codigo text primary key,  -- ej. 'PERM-PQRSD-009'
  nombre text not null,
  modulo text not null,  -- 'identidad', 'organizacion', 'ventanilla', 'pqrsd', 'documentos', 'firmas', 'trd', 'expedientes', 'reportes', 'auditoria', 'ia', 'correo', 'perifericos', etc.
  descripcion text,
  es_critico boolean not null default false,
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

comment on table gd.permiso is
  'GD-API-0001: catálogo de permisos GD. Seed inicial cubre ~140 permisos del '
  'PDF Matriz de Roles + 12 de EP-021 periféricos (PERM-PER-001..012).';

-- ----------------------------------------------------------------------------
-- 2.3 — GD-API-0001: Matriz rol ↔ permiso
-- ----------------------------------------------------------------------------
create table if not exists gd.rol_permiso (
  id uuid primary key default gen_random_uuid(),
  rol_codigo text not null references gd.rol(codigo) on delete restrict,
  permiso_codigo text not null references gd.permiso(codigo) on delete restrict,
  alcance_default text not null check (alcance_default in ('propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global')),
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (rol_codigo, permiso_codigo)
);

create index if not exists ix_gd_rol_permiso_rol on gd.rol_permiso(rol_codigo) where estado = 'activo';
create index if not exists ix_gd_rol_permiso_permiso on gd.rol_permiso(permiso_codigo) where estado = 'activo';

comment on table gd.rol_permiso is
  'GD-API-0001: matriz N:N entre gd.rol y gd.permiso. alcance_default es el '
  'alcance por defecto cuando se asigna el rol a un usuario (puede sobreescribirse '
  'por instancia en gd.asignacion_alcance).';

-- ----------------------------------------------------------------------------
-- 2.4 — GD-API-0001: Cargos institucionales
-- Vigencia se profundiza en EP-002 (GD-API-0013).
-- ----------------------------------------------------------------------------
create table if not exists gd.cargo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  nombre text not null,
  dependencia_id uuid,  -- FK añadida cuando gd.dependencia exista (EP-002)
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  fecha_inicio_vigencia date not null default current_date,
  fecha_fin_vigencia date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_cargo_tenant on gd.cargo(tenant_id);
create index if not exists ix_gd_cargo_dependencia on gd.cargo(dependencia_id) where dependencia_id is not null;

alter table gd.cargo enable row level security;

drop policy if exists cargo_tenant_isolation on gd.cargo;
create policy cargo_tenant_isolation on gd.cargo
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_cargo_updated_at
  before update on gd.cargo
  for each row execute function app.touch_updated_at();

comment on table gd.cargo is
  'GD-API-0001: cargos institucionales. Vigencia y snapshots se profundizan en '
  'EP-002 (GD-API-0013). El cargo usado en una firma o actuación se preserva '
  'como snapshot en core.evento_auditoria.actor_snapshot (RNF-006).';

-- ----------------------------------------------------------------------------
-- 2.5 — GD-API-0001: Perfil institucional del usuario (1:1 con app.users + tenant_id)
-- ----------------------------------------------------------------------------
create table if not exists gd.perfil_usuario (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,
  tipo_vinculacion text not null check (tipo_vinculacion in (
    'planta', 'provisional', 'ops', 'supernumerario', 'practicante',
    'externo_autorizado', 'administrador_tecnico'
  )),
  estado_gd text not null default 'activo' check (estado_gd in (
    'activo', 'suspendido', 'inactivo', 'bloqueado', 'retirado'
  )),
  fecha_inicio_vinculacion date not null default current_date,
  fecha_fin_vinculacion date,
  dependencia_actual_id uuid,  -- FK añadida cuando gd.dependencia exista (EP-002)
  cargo_actual_id uuid references gd.cargo(id) on delete restrict,
  ultimo_acceso timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict,
  unique (tenant_id, user_id)  -- un usuario, un perfil por tenant
);

create index if not exists ix_gd_perfil_usuario_tenant on gd.perfil_usuario(tenant_id);
create index if not exists ix_gd_perfil_usuario_user on gd.perfil_usuario(user_id);
create index if not exists ix_gd_perfil_usuario_estado on gd.perfil_usuario(tenant_id, estado_gd);
create index if not exists ix_gd_perfil_usuario_dependencia on gd.perfil_usuario(dependencia_actual_id)
  where dependencia_actual_id is not null;

alter table gd.perfil_usuario enable row level security;

drop policy if exists perfil_usuario_tenant_isolation on gd.perfil_usuario;
create policy perfil_usuario_tenant_isolation on gd.perfil_usuario
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_perfil_usuario_updated_at
  before update on gd.perfil_usuario
  for each row execute function app.touch_updated_at();

-- Trigger: bloquear DELETE (Mandato #3: no eliminación física).
create or replace function gd.perfil_usuario_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.perfil_usuario no admite DELETE. Use POST /api/v1/gd/perfil-usuario/{user_id}/retirar con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_perfil_usuario_no_delete on gd.perfil_usuario;
create trigger trg_gd_perfil_usuario_no_delete
  before delete on gd.perfil_usuario
  for each row execute function gd.perfil_usuario_block_delete();

comment on table gd.perfil_usuario is
  'GD-API-0001: 1:1 con app.users + tenant. Atributos institucionales que '
  'app.users no tiene (tipo_vinculacion, estado_gd, dependencia, cargo). '
  'NO duplica identidad — solo agrega contexto institucional. '
  'DELETE bloqueado por trigger (Mandato #3).';

-- ----------------------------------------------------------------------------
-- 2.6 — GD-API-0001: Asignación de rol con alcance por dependencia
-- ----------------------------------------------------------------------------
create table if not exists gd.asignacion_alcance (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,
  rol_codigo text not null references gd.rol(codigo) on delete restrict,
  dependencia_id uuid,  -- FK añadida cuando gd.dependencia exista (EP-002)
  alcance text not null check (alcance in ('propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global')),
  fecha_inicio date not null default current_date,
  fecha_fin date,
  estado text not null default 'activa' check (estado in ('activa', 'cerrada')),
  motivo text,
  asignado_por_user_id uuid references app.users(id) on delete restrict,
  motivo_cierre text,
  cerrado_por_user_id uuid references app.users(id) on delete restrict,
  cerrado_en timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_asignacion_alcance_user
  on gd.asignacion_alcance(user_id, tenant_id, estado);

create index if not exists ix_gd_asignacion_alcance_dependencia
  on gd.asignacion_alcance(dependencia_id, rol_codigo, estado)
  where dependencia_id is not null;

-- Índice parcial de asignaciones "activas". El predicado NO puede incluir
-- `current_date` porque PostgreSQL exige funciones IMMUTABLE en predicados
-- de índice (current_date es STABLE: cambia cada día). El filtro de
-- vigencia por fecha (`fecha_fin is null or fecha_fin >= current_date`)
-- se aplica en las queries que usan este índice. Mantener el predicado
-- mínimo (`estado = 'activa'`) sigue siendo útil: ~95% de los registros
-- históricamente quedan en estado != 'activa' al cabo de varios años,
-- por lo que el índice parcial mantiene el tamaño bajo control.
create index if not exists ix_gd_asignacion_alcance_vigentes
  on gd.asignacion_alcance(tenant_id, user_id)
  where estado = 'activa';

alter table gd.asignacion_alcance enable row level security;

drop policy if exists asignacion_alcance_tenant_isolation on gd.asignacion_alcance;
create policy asignacion_alcance_tenant_isolation on gd.asignacion_alcance
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_asignacion_alcance_updated_at
  before update on gd.asignacion_alcance
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: cerrar la asignación con fecha_fin y estado='cerrada' en su lugar.
create or replace function gd.asignacion_alcance_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.asignacion_alcance no admite DELETE. Use POST /api/v1/gd/usuarios/{user_id}/roles/{id}/cerrar con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_asignacion_alcance_no_delete on gd.asignacion_alcance;
create trigger trg_gd_asignacion_alcance_no_delete
  before delete on gd.asignacion_alcance
  for each row execute function gd.asignacion_alcance_block_delete();

comment on table gd.asignacion_alcance is
  'GD-API-0001: añade la dimensión "alcance por dependencia" que app.user_tenant_roles no tiene. '
  'Un usuario puede tener gd.profesional con alcance "Oficina Jurídica" y gd.usuario_consulta '
  'con alcance "toda la entidad" — dos filas distintas. Historial preservado (RNF-006): '
  'asignaciones cerradas se conservan permanentemente para reconstruir snapshots.';

-- ----------------------------------------------------------------------------
-- 2.7 — Helper function gd._rol_check_no_usage (referenciada en 2.1)
-- Implementación tardía porque depende de gd.asignacion_alcance.
-- ----------------------------------------------------------------------------
create or replace function gd._rol_check_no_usage()
returns trigger language plpgsql as $$
declare
  v_count int;
begin
  select count(*) into v_count
  from gd.asignacion_alcance
  where rol_codigo = old.codigo
    and estado = 'activa';

  if v_count > 0 then
    raise exception 'No se puede eliminar gd.rol "%": tiene % asignaciones activas. Use inactivación en su lugar.', old.codigo, v_count
      using errcode = '23503';  -- foreign_key_violation
  end if;

  return old;
end;
$$;

-- =============================================================================
-- 3. Bloque 2 — Política de contraseñas, historial y proveedor externo
-- =============================================================================
-- Tareas: GD-API-0007 (política + no-reuso N últimas + SSO stub).
-- Cierra GAP-4 (TRAZABILIDAD.md): el sistema actual valida complejidad pero
-- nunca el no-reuso histórico.
-- ----------------------------------------------------------------------------

-- 3.1 — Política de contraseñas (1 fila por tenant + 1 global default).
create table if not exists gd.politica_contrasena (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references app.tenants(id) on delete restrict,  -- NULL = default global
  longitud_minima int not null default 12 check (longitud_minima >= 6 and longitud_minima <= 256),
  complejidad_regex text not null default '^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w]).+$',
  historial_no_reuso int not null default 12 check (historial_no_reuso >= 0 and historial_no_reuso <= 100),
  vigencia_dias int not null default 90 check (vigencia_dias > 0 and vigencia_dias <= 3650),
  intentos_fallidos_max int not null default 5 check (intentos_fallidos_max > 0 and intentos_fallidos_max <= 100),
  cooldown_segundos int not null default 300 check (cooldown_segundos >= 0),
  vigente_desde timestamptz not null default now(),
  vigente_hasta timestamptz,
  estado text not null default 'activa' check (estado in ('activa', 'reemplazada')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict
);

create unique index if not exists ix_gd_politica_contrasena_tenant_vigente
  on gd.politica_contrasena(coalesce(tenant_id::text, 'GLOBAL'))
  where estado = 'activa';

alter table gd.politica_contrasena enable row level security;

drop policy if exists politica_contrasena_tenant_isolation on gd.politica_contrasena;
create policy politica_contrasena_tenant_isolation on gd.politica_contrasena
  for all
  using (tenant_id is null or tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id is null or tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_politica_contrasena_updated_at
  before update on gd.politica_contrasena
  for each row execute function app.touch_updated_at();

comment on table gd.politica_contrasena is
  'GD-API-0007: política de contraseñas por tenant (o global si tenant_id IS NULL). '
  'Solo una fila activa por tenant (índice único parcial). Cambios crean nueva fila '
  'y marcan la anterior como ''reemplazada'' (auditable con vigente_desde/hasta).';

-- 3.2 — Historial de contraseñas (cierra GAP-4 de TRAZABILIDAD.md).
create table if not exists gd.historico_contrasena (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,
  hash text not null,  -- bcrypt completo (incluye salt embebido)
  algoritmo text not null default 'bcrypt' check (algoritmo in ('bcrypt', 'argon2id')),
  creada_en timestamptz not null default now()
);

create index if not exists ix_gd_historico_contrasena_user_time
  on gd.historico_contrasena(user_id, tenant_id, creada_en desc);

alter table gd.historico_contrasena enable row level security;

drop policy if exists historico_contrasena_tenant_isolation on gd.historico_contrasena;
create policy historico_contrasena_tenant_isolation on gd.historico_contrasena
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- DELETE bloqueado: las contraseñas históricas no se eliminan, solo se purgan
-- por política de retención (más allá de gd.politica_contrasena.historial_no_reuso
-- + margen de seguridad). Esa purga la implementa un worker dedicado en el
-- futuro; por ahora, append-only.
create or replace function gd.historico_contrasena_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.historico_contrasena es append-only (no UPDATE/DELETE).'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_historico_contrasena_no_update on gd.historico_contrasena;
create trigger trg_gd_historico_contrasena_no_update
  before update on gd.historico_contrasena
  for each row execute function gd.historico_contrasena_block_mutations();

drop trigger if exists trg_gd_historico_contrasena_no_delete on gd.historico_contrasena;
create trigger trg_gd_historico_contrasena_no_delete
  before delete on gd.historico_contrasena
  for each row execute function gd.historico_contrasena_block_mutations();

comment on table gd.historico_contrasena is
  'GD-API-0007 / GAP-4: hashes históricos de las últimas N contraseñas de cada '
  'usuario para validar no-reuso. Append-only; purga futura por worker.';

-- 3.3 — Stub de proveedor de identidad externo (SSO/SAML/LDAP/AD).
create table if not exists gd.proveedor_identidad_externo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo text not null check (tipo in ('saml', 'oidc', 'ldap', 'active_directory')),
  nombre text not null,
  configuracion jsonb not null default '{}'::jsonb,  -- cifrada por columna en fase 2
  estado text not null default 'configurado' check (estado in ('configurado', 'activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, nombre)
);

alter table gd.proveedor_identidad_externo enable row level security;

drop policy if exists proveedor_identidad_tenant_isolation on gd.proveedor_identidad_externo;
create policy proveedor_identidad_tenant_isolation on gd.proveedor_identidad_externo
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_proveedor_identidad_updated_at
  before update on gd.proveedor_identidad_externo
  for each row execute function app.touch_updated_at();

comment on table gd.proveedor_identidad_externo is
  'GD-API-0007: stub para futura integración SSO/SAML/LDAP/AD (fase 2). '
  'En este bloque solo existe la tabla; los endpoints CRUD se difieren al bloque '
  'donde se implemente el conector real.';

-- =============================================================================
-- 4. Bloque 3 — Snapshot identidad, perfil organización, módulos activables,
--    defaults por tipo, estructura orgánica versionada.
-- =============================================================================
-- Tareas: GD-API-0009, GD-API-0011, GD-API-0011.b, GD-API-0011.c, GD-API-0012.
-- (GD-API-0010 genera markdown en docs/; GD-API-0013/0014 quedan al bloque 4.)
-- ----------------------------------------------------------------------------

-- 4.1 — GD-API-0009: función `gd.capturar_snapshot_actuacion(usuario_id)`.
-- Retorna el snapshot inmutable que toda actuación (firma, asignación,
-- evento de auditoría, etc.) debe persistir. Cambios futuros de rol/cargo/
-- dependencia NO alteran este snapshot. RNF-006.
--
-- NOTA: el snapshot consulta al perfil GD vigente del usuario en el tenant
-- ACTUAL (RLS lo restringe). Como el snapshot lo invocan handlers que ya
-- tienen tenant_id seteado en GUC, no requiere parámetro de tenant.
-- ----------------------------------------------------------------------------
create or replace function gd.capturar_snapshot_actuacion(p_user_id uuid)
returns jsonb language plpgsql stable as $$
declare
  v_snapshot jsonb;
begin
  -- LEFT JOINs porque dependencia/cargo pueden ser NULL (no obligatorios).
  select jsonb_build_object(
    'usuario_id', u.id,
    'nombre_completo', u.display_name,
    'email', u.email::text,
    'tipo_vinculacion', p.tipo_vinculacion,
    'estado_gd', p.estado_gd,
    'dependencia_id', p.dependencia_actual_id,
    'dependencia_nombre', d.nombre,
    'dependencia_codigo', d.codigo_organico,
    'cargo_id', p.cargo_actual_id,
    'cargo_nombre', c.nombre,
    'capturado_en', now()
  )
  into v_snapshot
  from app.users u
  left join gd.perfil_usuario p
    on p.user_id = u.id and p.tenant_id = app.current_tenant_id()
  left join gd.dependencia d on d.id = p.dependencia_actual_id
  left join gd.cargo c on c.id = p.cargo_actual_id
  where u.id = p_user_id;

  if v_snapshot is null then
    raise exception 'usuario % no encontrado al capturar snapshot', p_user_id
      using errcode = 'P0002';  -- no_data_found
  end if;

  return v_snapshot;
end;
$$;

comment on function gd.capturar_snapshot_actuacion is
  'GD-API-0009: captura snapshot inmutable del actor para auditar actuaciones. '
  'RNF-006 exige que firmas/asignaciones/eventos conserven el rol/cargo/'
  'dependencia HISTÓRICO, no la versión actual. Llamar desde handlers ANTES '
  'de insertar el evento.';

-- ----------------------------------------------------------------------------
-- 4.2 — GD-API-0011: gd.perfil_organizacion (1:1 con app.tenants).
-- Neutro de sector: tipo_organizacion ∈ {publica, privada, mixta, ong,
-- gremial, cooperativa}. Cubre Colombia (NIT) + LATAM (RFC, CUIT, EIN).
-- ----------------------------------------------------------------------------
create table if not exists gd.perfil_organizacion (
  tenant_id uuid primary key references app.tenants(id) on delete restrict,
  tipo_organizacion text not null
    check (tipo_organizacion in ('publica', 'privada', 'mixta', 'ong', 'gremial', 'cooperativa')),
  identificacion_fiscal text not null,  -- NIT/RFC/CUIT/EIN
  tipo_identificacion_fiscal text not null default 'NIT'
    check (tipo_identificacion_fiscal in ('NIT', 'RFC', 'CUIT', 'EIN', 'CNPJ', 'RUT', 'OTRO')),
  razon_social_legal text not null,
  nombre_corto text not null,
  direccion_oficial text,
  telefono_oficial text,
  correo_oficial text,
  sitio_web text,
  -- D7: FK a core.archivo_digital se difiere hasta EP-018. Por ahora UUID
  -- sin FK formal; el job que cree el archivo logo retornará el id y lo
  -- guardará aquí. Cuando EP-018 corra: ALTER TABLE add constraint.
  logo_archivo_digital_id uuid,
  politica_firma_default text not null default 'electronica'
    check (politica_firma_default in ('escaneada', 'electronica', 'digital_certificada')),
  formato_radicado text not null default '{prefijo}-{vigencia}-{consecutivo:06d}',
  dias_alerta_vencimiento_default int not null default 3 check (dias_alerta_vencimiento_default > 0),
  pais_iso char(2) not null default 'CO',
  zona_horaria_default text not null default 'America/Bogota',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict
);

alter table gd.perfil_organizacion enable row level security;

drop policy if exists perfil_organizacion_tenant_isolation on gd.perfil_organizacion;
create policy perfil_organizacion_tenant_isolation on gd.perfil_organizacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_perfil_organizacion_updated_at
  before update on gd.perfil_organizacion
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado (Mandato #3): inactivar el tenant en su lugar.
create or replace function gd.perfil_organizacion_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.perfil_organizacion no admite DELETE. Use inactivación del tenant.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_perfil_organizacion_no_delete on gd.perfil_organizacion;
create trigger trg_gd_perfil_organizacion_no_delete
  before delete on gd.perfil_organizacion
  for each row execute function gd.perfil_organizacion_block_delete();

comment on table gd.perfil_organizacion is
  'GD-API-0011: 1:1 con app.tenants. Campos institucionales que tenants no tiene. '
  'Neutro de sector: tipo_organizacion ∈ {publica, privada, mixta, ong, gremial, cooperativa}. '
  'logo_archivo_digital_id sin FK formal hasta EP-018 (decisión D7).';

-- ----------------------------------------------------------------------------
-- 4.3 — GD-API-0011.b: gd.organizacion_modulo_activacion.
-- Feature flags por organización para los 14 módulos individualmente activables.
-- ----------------------------------------------------------------------------
create table if not exists gd.organizacion_modulo_activacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  modulo_codigo text not null check (modulo_codigo in (
    'pqrsd_legal',
    'pqrsd_tickets',
    'correspondencia_interna',
    'correspondencia_externa',
    'firma_escaneada',
    'firma_electronica',
    'firma_digital_certificada',
    'expedientes',
    'trd_tvd',
    'integracion_correo',
    'agentes_ia',
    'radicacion_externa_desde_dependencia',
    'consulta_publica_radicado',
    'ventanilla_presencial_con_perifericos'
  )),
  activado boolean not null default false,
  configuracion jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, modulo_codigo)
);

create index if not exists ix_gd_org_modulos_tenant
  on gd.organizacion_modulo_activacion(tenant_id)
  where activado = true;

alter table gd.organizacion_modulo_activacion enable row level security;

drop policy if exists org_modulos_tenant_isolation on gd.organizacion_modulo_activacion;
create policy org_modulos_tenant_isolation on gd.organizacion_modulo_activacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_org_modulos_updated_at
  before update on gd.organizacion_modulo_activacion
  for each row execute function app.touch_updated_at();

comment on table gd.organizacion_modulo_activacion is
  'GD-API-0011.b: feature flags por organización. 14 módulos activables. '
  'consulta_publica_radicado y ventanilla_presencial_con_perifericos típicamente '
  'inactivos en organizaciones privadas.';

-- ----------------------------------------------------------------------------
-- 4.4 — GD-API-0011.c: función `gd.aplicar_defaults_modulos(tenant_id)`.
-- Aplica defaults sensatos por tipo_organizacion al crear el perfil.
-- ----------------------------------------------------------------------------
create or replace function gd.aplicar_defaults_modulos(p_tenant_id uuid)
returns int language plpgsql as $$
declare
  v_tipo text;
  v_filas_insertadas int := 0;
  -- Mapa: tipo_organizacion → set de módulos activos por default.
  -- Empresa privada solo módulos esenciales; pública/mixta todo; ONG con expedientes.
  v_modulos_publica text[] := array[
    'pqrsd_legal', 'correspondencia_interna', 'correspondencia_externa',
    'firma_escaneada', 'firma_electronica', 'expedientes', 'trd_tvd',
    'integracion_correo', 'agentes_ia', 'radicacion_externa_desde_dependencia',
    'consulta_publica_radicado', 'ventanilla_presencial_con_perifericos'
  ];
  v_modulos_privada text[] := array[
    'correspondencia_interna', 'correspondencia_externa',
    'firma_electronica', 'integracion_correo', 'agentes_ia'
  ];
  v_modulos_ong text[] := array[
    'correspondencia_interna', 'correspondencia_externa',
    'firma_electronica', 'expedientes', 'integracion_correo', 'agentes_ia'
  ];
  v_modulos_mixta text[] := v_modulos_publica;  -- igual a pública por default
  v_modulos_activos text[];
  v_modulo text;
  v_inserted_count int;
begin
  select tipo_organizacion into v_tipo
  from gd.perfil_organizacion
  where tenant_id = p_tenant_id;

  if v_tipo is null then
    raise exception 'no existe gd.perfil_organizacion para tenant %', p_tenant_id
      using errcode = 'P0002';
  end if;

  v_modulos_activos := case v_tipo
    when 'publica'    then v_modulos_publica
    when 'privada'    then v_modulos_privada
    when 'ong'        then v_modulos_ong
    when 'mixta'      then v_modulos_mixta
    when 'gremial'    then v_modulos_privada  -- similar a privada
    when 'cooperativa' then v_modulos_privada
    else v_modulos_privada
  end;

  -- INSERT idempotente (no sobrescribe activaciones manuales).
  foreach v_modulo in array v_modulos_activos loop
    insert into gd.organizacion_modulo_activacion (tenant_id, modulo_codigo, activado)
    values (p_tenant_id, v_modulo, true)
    on conflict (tenant_id, modulo_codigo) do nothing;
    -- GET DIAGNOSTICS porque `found` no se setea con ON CONFLICT DO NOTHING.
    get diagnostics v_inserted_count = row_count;
    v_filas_insertadas := v_filas_insertadas + v_inserted_count;
  end loop;

  return v_filas_insertadas;
end;
$$;

comment on function gd.aplicar_defaults_modulos is
  'GD-API-0011.c: aplica feature flags default según tipo_organizacion. '
  'Idempotente: no sobrescribe activaciones manuales previas. Retorna número '
  'de módulos efectivamente insertados.';

-- ----------------------------------------------------------------------------
-- 4.5 — GD-API-0012: estructura orgánica versionada.
-- gd.version_estructura_organica → gd.dependencia (con vigencia + padre).
-- ----------------------------------------------------------------------------
create table if not exists gd.version_estructura_organica (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  numero_version text not null,
  descripcion text,
  acto_administrativo text,
  fecha_inicio_vigencia date not null default current_date,
  fecha_fin_vigencia date,
  estado text not null default 'borrador'
    check (estado in ('borrador', 'vigente', 'cerrada', 'historica')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict,
  unique (tenant_id, numero_version)
);

-- Una sola versión vigente por tenant (índice único parcial).
create unique index if not exists ix_gd_vestruct_vigente_unica
  on gd.version_estructura_organica(tenant_id)
  where estado = 'vigente';

alter table gd.version_estructura_organica enable row level security;

drop policy if exists vestruct_tenant_isolation on gd.version_estructura_organica;
create policy vestruct_tenant_isolation on gd.version_estructura_organica
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_vestruct_updated_at
  before update on gd.version_estructura_organica
  for each row execute function app.touch_updated_at();

comment on table gd.version_estructura_organica is
  'GD-API-0012: versiones de estructura orgánica institucional. Solo una '
  'vigente por tenant (índice único parcial). Versiones cerradas/históricas '
  'preservan radicados antiguos (RNF-026).';

-- ----------------------------------------------------------------------------
-- gd.dependencia: ya tenía FKs referenciadas en bloque 1 (perfil_usuario,
-- cargo, asignacion_alcance, version_estructura_organica). Ahora la creamos.
-- ----------------------------------------------------------------------------
create table if not exists gd.dependencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  codigo_organico text not null,
  nombre text not null,
  dependencia_padre_id uuid references gd.dependencia(id) on delete restrict,
  version_estructura_id uuid not null references gd.version_estructura_organica(id) on delete restrict,
  estado text not null default 'activa'
    check (estado in ('activa', 'inactiva', 'cerrada', 'fusionada')),
  fecha_inicio_vigencia date not null default current_date,
  fecha_fin_vigencia date,
  motivo_cierre text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict,
  unique (tenant_id, codigo_organico, version_estructura_id)
);

create index if not exists ix_gd_dependencia_tenant on gd.dependencia(tenant_id);
create index if not exists ix_gd_dependencia_padre
  on gd.dependencia(dependencia_padre_id)
  where dependencia_padre_id is not null;
create index if not exists ix_gd_dependencia_version
  on gd.dependencia(version_estructura_id);
create index if not exists ix_gd_dependencia_vigentes
  on gd.dependencia(tenant_id, estado)
  where estado = 'activa';

alter table gd.dependencia enable row level security;

drop policy if exists dependencia_tenant_isolation on gd.dependencia;
create policy dependencia_tenant_isolation on gd.dependencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_dependencia_updated_at
  before update on gd.dependencia
  for each row execute function app.touch_updated_at();

create or replace function gd.dependencia_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.dependencia no admite DELETE. Use cierre de vigencia.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_dependencia_no_delete on gd.dependencia;
create trigger trg_gd_dependencia_no_delete
  before delete on gd.dependencia
  for each row execute function gd.dependencia_block_delete();

comment on table gd.dependencia is
  'GD-API-0012: dependencias institucionales versionadas. Cambio de nombre/'
  'jerarquía obliga abrir nueva versión (RNF-026). Radicados conservan la '
  'dependencia histórica vigente al momento de creación.';

-- ----------------------------------------------------------------------------
-- ALTER de FKs deferidas del bloque 1:
-- gd.perfil_usuario.dependencia_actual_id, gd.cargo.dependencia_id,
-- gd.asignacion_alcance.dependencia_id → todas apuntan a gd.dependencia(id).
-- Las creamos como NOT VALID + VALIDATE separado para no romper datos
-- históricos posibles (las tablas estarán vacías al primer deploy).
-- ----------------------------------------------------------------------------
do $$
begin
  -- gd.perfil_usuario.dependencia_actual_id
  if not exists (
    select 1 from pg_constraint
    where conname = 'fk_gd_perfil_usuario_dependencia'
  ) then
    alter table gd.perfil_usuario
      add constraint fk_gd_perfil_usuario_dependencia
      foreign key (dependencia_actual_id) references gd.dependencia(id)
      on delete restrict
      not valid;
    alter table gd.perfil_usuario validate constraint fk_gd_perfil_usuario_dependencia;
  end if;

  -- gd.cargo.dependencia_id
  if not exists (
    select 1 from pg_constraint
    where conname = 'fk_gd_cargo_dependencia'
  ) then
    alter table gd.cargo
      add constraint fk_gd_cargo_dependencia
      foreign key (dependencia_id) references gd.dependencia(id)
      on delete restrict
      not valid;
    alter table gd.cargo validate constraint fk_gd_cargo_dependencia;
  end if;

  -- gd.asignacion_alcance.dependencia_id
  if not exists (
    select 1 from pg_constraint
    where conname = 'fk_gd_asignacion_alcance_dependencia'
  ) then
    alter table gd.asignacion_alcance
      add constraint fk_gd_asignacion_alcance_dependencia
      foreign key (dependencia_id) references gd.dependencia(id)
      on delete restrict
      not valid;
    alter table gd.asignacion_alcance validate constraint fk_gd_asignacion_alcance_dependencia;
  end if;
end $$;

-- =============================================================================
-- 5. Bloque 4 — Catálogos institucionales + parámetros + reglas comunicación +
--    consecutivos radicación.
-- =============================================================================
-- Tareas: GD-API-0014 (canales/calendarios/tipos PQRSD/correspondencia),
--         GD-API-0015 (parámetros versionados),
--         GD-API-0016 (reglas comunicación entre dependencias),
--         GD-API-0023 (consecutivos transaccionales radicación).
-- GD-API-0013 (cargos) ya tenía tabla gd.cargo desde bloque 1; este bloque
-- agrega los endpoints CRUD y reglas de vigencia en Python.
-- ----------------------------------------------------------------------------

-- 5.1 — GD-API-0014: gd.canal (medios de recepción/envío).
create table if not exists gd.canal (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  codigo text not null,
  nombre text not null,
  descripcion text,
  requiere_punto_atencion boolean not null default false,
  requiere_digitalizacion boolean not null default false,
  permite_acuse boolean not null default true,
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, codigo)
);

alter table gd.canal enable row level security;

drop policy if exists canal_tenant_isolation on gd.canal;
create policy canal_tenant_isolation on gd.canal
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_canal_updated_at
  before update on gd.canal
  for each row execute function app.touch_updated_at();

comment on table gd.canal is
  'GD-API-0014: medios de recepción/envío (presencial, correo postal, web, '
  'WhatsApp, etc.). Requiere_punto_atencion=true exige radicar con punto_atencion_id.';

-- ----------------------------------------------------------------------------
-- 5.2 — GD-API-0014: gd.calendario_institucional (días hábiles + festivos).
-- ----------------------------------------------------------------------------
create table if not exists gd.calendario_institucional (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  nombre text not null,
  vigencia_anual int not null check (vigencia_anual between 2020 and 2100),
  -- Festivos como array de fechas. JSON para flexibilidad (puede tener
  -- estructura adicional como motivo o región en el futuro).
  festivos jsonb not null default '[]'::jsonb,
  -- Días de la semana NO laborales (0=domingo, 6=sábado en convención SQL).
  dias_no_laborales smallint[] not null default array[0, 6]::smallint[],
  es_default boolean not null default false,
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, nombre, vigencia_anual)
);

create unique index if not exists ix_gd_calendario_default_unico
  on gd.calendario_institucional(tenant_id)
  where es_default = true and estado = 'activo';

alter table gd.calendario_institucional enable row level security;

drop policy if exists calendario_tenant_isolation on gd.calendario_institucional;
create policy calendario_tenant_isolation on gd.calendario_institucional
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_calendario_updated_at
  before update on gd.calendario_institucional
  for each row execute function app.touch_updated_at();

comment on table gd.calendario_institucional is
  'GD-API-0014: calendarios laborales. festivos como jsonb permite metadata '
  'futura (región, motivo). Solo un calendario default activo por tenant.';

-- ----------------------------------------------------------------------------
-- 5.3 — GD-API-0014: función gd.calcular_fecha_limite() — clave para EP-007.
-- Suma N días hábiles o calendario a una fecha base saltando fin de semana y
-- festivos según el calendario default del tenant.
-- ----------------------------------------------------------------------------
create or replace function gd.calcular_fecha_limite(
  p_tenant_id uuid,
  p_fecha_base timestamptz,
  p_termino_dias int,
  p_tipo_dias text  -- 'habiles' o 'calendario'
) returns timestamptz language plpgsql stable as $$
declare
  v_fecha_actual date := p_fecha_base::date;
  v_dias_sumados int := 0;
  v_festivos jsonb;
  v_dias_no_laborales smallint[];
  v_es_no_laboral boolean;
begin
  if p_termino_dias < 0 then
    raise exception 'p_termino_dias debe ser >= 0';
  end if;

  if p_tipo_dias not in ('habiles', 'calendario') then
    raise exception 'p_tipo_dias debe ser ''habiles'' o ''calendario''';
  end if;

  if p_termino_dias = 0 then
    return p_fecha_base;
  end if;

  if p_tipo_dias = 'calendario' then
    -- Trivial: suma directa de días.
    return p_fecha_base + (p_termino_dias || ' days')::interval;
  end if;

  -- 'habiles': cargar calendario default activo del tenant.
  select festivos, dias_no_laborales
  into v_festivos, v_dias_no_laborales
  from gd.calendario_institucional
  where tenant_id = p_tenant_id
    and es_default = true
    and estado = 'activo'
    and vigencia_anual = extract(year from p_fecha_base)::int
  limit 1;

  -- Fallback razonable si el tenant no tiene calendario configurado:
  -- usar fin de semana estándar (sábado=6, domingo=0) y array vacío de festivos.
  if v_dias_no_laborales is null then
    v_dias_no_laborales := array[0, 6]::smallint[];
    v_festivos := '[]'::jsonb;
  end if;

  -- Loop: avanzar 1 día y contar si es hábil.
  while v_dias_sumados < p_termino_dias loop
    v_fecha_actual := v_fecha_actual + 1;

    -- ¿Es día de fin de semana?
    v_es_no_laboral := extract(dow from v_fecha_actual)::smallint = any(v_dias_no_laborales);

    -- ¿Es festivo del calendario?
    if not v_es_no_laboral then
      v_es_no_laboral := v_festivos ? to_char(v_fecha_actual, 'YYYY-MM-DD');
    end if;

    if not v_es_no_laboral then
      v_dias_sumados := v_dias_sumados + 1;
    end if;
  end loop;

  -- Conservar hora original.
  return v_fecha_actual::timestamptz + (p_fecha_base::time)::interval;
end;
$$;

comment on function gd.calcular_fecha_limite is
  'GD-API-0014: calcula fecha límite saltando fin de semana + festivos según '
  'calendario default del tenant. Usado por EP-007 al crear PQRSD.';

-- ----------------------------------------------------------------------------
-- 5.4 — GD-API-0014: gd.tipo_pqrsd (catálogo con términos legales).
-- ----------------------------------------------------------------------------
create table if not exists gd.tipo_pqrsd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  codigo text not null,
  nombre text not null,
  descripcion text,
  termino_dias int not null check (termino_dias > 0),
  tipo_dias text not null check (tipo_dias in ('habiles', 'calendario')),
  requiere_respuesta boolean not null default true,
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, codigo)
);

alter table gd.tipo_pqrsd enable row level security;

drop policy if exists tipo_pqrsd_tenant_isolation on gd.tipo_pqrsd;
create policy tipo_pqrsd_tenant_isolation on gd.tipo_pqrsd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tipo_pqrsd_updated_at
  before update on gd.tipo_pqrsd
  for each row execute function app.touch_updated_at();

comment on table gd.tipo_pqrsd is
  'GD-API-0014: tipos de PQRSD con sus términos legales. Ej: petición=15 días '
  'hábiles (Colombia Ley 1755). Configurable por tenant porque cada país/'
  'sector tiene reglas distintas.';

-- ----------------------------------------------------------------------------
-- 5.5 — GD-API-0014: gd.tipo_correspondencia.
-- ----------------------------------------------------------------------------
create table if not exists gd.tipo_correspondencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  codigo text not null,
  nombre text not null,
  descripcion text,
  ambito text not null check (ambito in ('interna', 'externa_recibida', 'externa_enviada')),
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, codigo)
);

alter table gd.tipo_correspondencia enable row level security;

drop policy if exists tipo_corresp_tenant_isolation on gd.tipo_correspondencia;
create policy tipo_corresp_tenant_isolation on gd.tipo_correspondencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tipo_corresp_updated_at
  before update on gd.tipo_correspondencia
  for each row execute function app.touch_updated_at();

-- ----------------------------------------------------------------------------
-- 5.6 — GD-API-0015: parámetros institucionales versionados.
-- ----------------------------------------------------------------------------
create table if not exists gd.parametro (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  clave text not null,
  valor text not null,
  tipo text not null default 'string' check (tipo in ('string', 'integer', 'boolean', 'json', 'decimal')),
  descripcion text,
  vigente_desde timestamptz not null default now(),
  vigente_hasta timestamptz,
  estado text not null default 'activo' check (estado in ('activo', 'reemplazado')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict
);

create unique index if not exists ix_gd_parametro_clave_activo
  on gd.parametro(tenant_id, clave)
  where estado = 'activo';

create index if not exists ix_gd_parametro_historico
  on gd.parametro(tenant_id, clave, vigente_desde desc);

alter table gd.parametro enable row level security;

drop policy if exists parametro_tenant_isolation on gd.parametro;
create policy parametro_tenant_isolation on gd.parametro
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_parametro_updated_at
  before update on gd.parametro
  for each row execute function app.touch_updated_at();

comment on table gd.parametro is
  'GD-API-0015: parámetros clave-valor versionados. Cada cambio crea nueva '
  'fila + marca anterior reemplazada (RNF-009). Solo una activa por '
  '(tenant, clave) — índice único parcial.';

-- ----------------------------------------------------------------------------
-- 5.7 — GD-API-0016: reglas de comunicación entre dependencias.
-- ----------------------------------------------------------------------------
create table if not exists gd.regla_comunicacion_interdependencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  dependencia_origen_id uuid not null references gd.dependencia(id) on delete restrict,
  dependencia_destino_id uuid not null references gd.dependencia(id) on delete restrict,
  permitido boolean not null default true,
  requiere_aprobacion_jefe boolean not null default false,
  motivo_restriccion text,
  estado text not null default 'activa' check (estado in ('activa', 'inactiva')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict,
  unique (tenant_id, dependencia_origen_id, dependencia_destino_id)
);

create index if not exists ix_gd_regla_origen
  on gd.regla_comunicacion_interdependencia(tenant_id, dependencia_origen_id)
  where estado = 'activa';

alter table gd.regla_comunicacion_interdependencia enable row level security;

drop policy if exists regla_comunicacion_tenant_isolation
  on gd.regla_comunicacion_interdependencia;
create policy regla_comunicacion_tenant_isolation
  on gd.regla_comunicacion_interdependencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_regla_comunicacion_updated_at
  before update on gd.regla_comunicacion_interdependencia
  for each row execute function app.touch_updated_at();

comment on table gd.regla_comunicacion_interdependencia is
  'GD-API-0016: reglas explícitas de qué dependencias pueden comunicarse. '
  'Default permisivo: si no hay fila, se asume permitido. EP-008 valida '
  'antes de crear correspondencia interna.';

-- ----------------------------------------------------------------------------
-- 5.8 — GD-API-0023: consecutivos transaccionales por vigencia + tipo.
-- ----------------------------------------------------------------------------
create table if not exists gd.consecutivo_radicacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  vigencia int not null check (vigencia between 2020 and 2100),
  tipo_radicado text not null check (tipo_radicado in ('entrada', 'salida', 'interno', 'otro')),
  prefijo text not null default 'RAD',
  ultimo_numero bigint not null default 0,
  formato text not null default '{prefijo}-{vigencia}-{consecutivo:06d}',
  estado text not null default 'activo' check (estado in ('activo', 'cerrado')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, vigencia, tipo_radicado)
);

alter table gd.consecutivo_radicacion enable row level security;

drop policy if exists consecutivo_tenant_isolation on gd.consecutivo_radicacion;
create policy consecutivo_tenant_isolation on gd.consecutivo_radicacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_consecutivo_updated_at
  before update on gd.consecutivo_radicacion
  for each row execute function app.touch_updated_at();

-- ----------------------------------------------------------------------------
-- gd.siguiente_radicado(): atómica con SELECT FOR UPDATE.
-- Crea la fila de consecutivo si no existe (auto-init de vigencia anual).
-- Aplica el formato configurado: {prefijo}-{vigencia}-{consecutivo:06d}.
-- ----------------------------------------------------------------------------
create or replace function gd.siguiente_radicado(
  p_tenant_id uuid,
  p_vigencia int,
  p_tipo_radicado text
) returns text language plpgsql as $$
declare
  v_id uuid;
  v_prefijo text;
  v_formato text;
  v_nuevo_numero bigint;
  v_resultado text;
begin
  if p_tipo_radicado not in ('entrada', 'salida', 'interno', 'otro') then
    raise exception 'tipo_radicado inválido: %', p_tipo_radicado;
  end if;

  -- Auto-init si no existe la fila para esta vigencia+tipo+tenant.
  insert into gd.consecutivo_radicacion (tenant_id, vigencia, tipo_radicado)
  values (p_tenant_id, p_vigencia, p_tipo_radicado)
  on conflict (tenant_id, vigencia, tipo_radicado) do nothing;

  -- Incremento atómico con FOR UPDATE.
  update gd.consecutivo_radicacion
  set ultimo_numero = ultimo_numero + 1
  where tenant_id = p_tenant_id
    and vigencia = p_vigencia
    and tipo_radicado = p_tipo_radicado
    and estado = 'activo'
  returning id, prefijo, formato, ultimo_numero
  into v_id, v_prefijo, v_formato, v_nuevo_numero;

  if v_id is null then
    raise exception 'consecutivo agotado o cerrado para tenant=% vigencia=% tipo=%',
      p_tenant_id, p_vigencia, p_tipo_radicado
      using errcode = 'P0001';
  end if;

  -- Aplicar formato: reemplaza {prefijo}, {vigencia}, {consecutivo:NNd}.
  -- Para v1 soportamos solo el formato canónico documentado: {prefijo}-{vigencia}-{consecutivo:06d}.
  v_resultado := v_prefijo || '-' || p_vigencia::text || '-' ||
                 lpad(v_nuevo_numero::text, 6, '0');

  return v_resultado;
end;
$$;

comment on function gd.siguiente_radicado is
  'GD-API-0023: genera el siguiente número de radicado de forma atómica. '
  'Auto-init de vigencia anual. SELECT FOR UPDATE evita duplicados bajo '
  'concurrencia. Formato fijo v1: {prefijo}-{vigencia}-{consecutivo:06d}.';

-- =============================================================================
-- 6. Bloque 5 — Ventanilla Única (radicación) + Terceros.
-- =============================================================================
-- Tareas: GD-API-0024..0029 (radicado entrada/salida + clasificación +
--         anulación + búsqueda), GD-API-0033 (terceros — dependencia de 0024).
-- ----------------------------------------------------------------------------

-- 6.1 — GD-API-0033: gd.tercero (ciudadanos/empresas/entidades externas).
create table if not exists gd.tercero (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo_tercero text not null check (tipo_tercero in (
    'persona_natural', 'persona_juridica', 'entidad_publica',
    'entidad_privada', 'anonimo'
  )),
  tipo_documento text check (tipo_documento in (
    'CC', 'CE', 'NIT', 'pasaporte', 'otro', 'sin_documento'
  )),
  numero_documento text,
  nombres_razon_social text not null,
  correo text,
  telefono text,
  direccion text,
  municipio text,
  departamento text,
  pais char(2) not null default 'CO',
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  created_by_user_id uuid references app.users(id) on delete restrict
);

-- Índice único parcial: el documento es único PER tenant salvo terceros anónimos
-- (que pueden ser muchos sin documento).
create unique index if not exists ix_gd_tercero_documento_unico
  on gd.tercero(tenant_id, tipo_documento, numero_documento)
  where tipo_tercero != 'anonimo' and numero_documento is not null;

-- Búsqueda rápida por nombre/email (RNF-044).
create index if not exists ix_gd_tercero_busqueda_nombre
  on gd.tercero using gin (to_tsvector('spanish', nombres_razon_social));
create index if not exists ix_gd_tercero_correo
  on gd.tercero(tenant_id, lower(correo))
  where correo is not null;

alter table gd.tercero enable row level security;

drop policy if exists tercero_tenant_isolation on gd.tercero;
create policy tercero_tenant_isolation on gd.tercero
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tercero_updated_at
  before update on gd.tercero
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: terceros con radicados deben preservarse para auditoría.
create or replace function gd.tercero_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.tercero no admite DELETE. Use inactivación.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_tercero_no_delete on gd.tercero;
create trigger trg_gd_tercero_no_delete
  before delete on gd.tercero
  for each row execute function gd.tercero_block_delete();

comment on table gd.tercero is
  'GD-API-0033: ciudadanos/empresas/entidades externas (remitentes/destinatarios). '
  'Anónimos permitidos: tipo_tercero=anonimo + numero_documento NULL. '
  'Unique por (tipo_doc, numero_doc) solo para no-anónimos.';

-- 6.2 — gd.contacto_tercero (canales de contacto múltiples).
create table if not exists gd.contacto_tercero (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tercero_id uuid not null references gd.tercero(id) on delete restrict,
  tipo_contacto text not null check (tipo_contacto in (
    'correo', 'telefono', 'celular', 'direccion'
  )),
  valor text not null,
  es_principal boolean not null default false,
  estado text not null default 'activo' check (estado in ('activo', 'inactivo')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_contacto_tercero
  on gd.contacto_tercero(tercero_id);

alter table gd.contacto_tercero enable row level security;

drop policy if exists contacto_tercero_tenant_isolation on gd.contacto_tercero;
create policy contacto_tercero_tenant_isolation on gd.contacto_tercero
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_contacto_tercero_updated_at
  before update on gd.contacto_tercero
  for each row execute function app.touch_updated_at();

-- ----------------------------------------------------------------------------
-- 6.3 — GD-API-0024: gd.radicado (el corazón del módulo).
-- ----------------------------------------------------------------------------
create table if not exists gd.radicado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  -- Número oficial — INMUTABLE (RNF-011). Único por tenant.
  numero_radicado text not null,
  tipo_radicado text not null check (tipo_radicado in (
    'entrada', 'salida', 'interno', 'otro'
  )),
  fecha_radicacion timestamptz not null default now(),
  canal_id uuid not null references gd.canal(id) on delete restrict,
  punto_atencion_id uuid,  -- FK deferida a EP-021 (gd.punto_atencion no existe aún)
  asunto text not null,
  descripcion text,
  -- Terceros
  tercero_id uuid references gd.tercero(id) on delete restrict,
  tercero_destinatario_id uuid references gd.tercero(id) on delete restrict,
  -- Dependencias (FK ya válida desde bloque 3)
  dependencia_origen_id uuid references gd.dependencia(id) on delete restrict,
  dependencia_destino_id uuid references gd.dependencia(id) on delete restrict,
  -- Documento principal (solo para salidas — FK deferida a EP-009)
  documento_principal_id uuid,
  -- Quien radicó
  usuario_radicador_id uuid not null references app.users(id) on delete restrict,
  -- Estado del radicado
  estado text not null default 'registrado' check (estado in (
    'registrado', 'clasificado', 'en_gestion', 'cerrado', 'anulado'
  )),
  -- Radicado relacionado (entrada-salida o salida-entrada)
  radicado_relacionado_id uuid references gd.radicado(id) on delete restrict,
  -- Código de verificación público (6 chars alfanumérico, sin 0/O/1/I/l)
  codigo_verificacion text not null,
  -- Flags especiales
  es_radicacion_contingencia boolean not null default false,
  fecha_radicacion_real timestamptz,  -- solo si es_radicacion_contingencia=true
  evidencia_contingencia_archivo_digital_id uuid,
  -- Snapshot del actor radicador (RNF-006)
  actor_snapshot jsonb not null default '{}'::jsonb,
  -- Metadata adicional
  metadata jsonb not null default '{}'::jsonb,
  -- Timestamps
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  anulado_en timestamptz,
  anulado_por_user_id uuid references app.users(id) on delete restrict,
  motivo_anulacion text
);

-- Único por tenant + numero_radicado.
create unique index if not exists ix_gd_radicado_numero_unico
  on gd.radicado(tenant_id, numero_radicado);

-- Único por código verificación (público) — debe ser globalmente único o al
-- menos único por tenant. Hacemos por tenant para evitar leaks cross-tenant.
create unique index if not exists ix_gd_radicado_codigo_verif_unico
  on gd.radicado(tenant_id, codigo_verificacion);

-- Índices para búsqueda (RNF-039).
create index if not exists ix_gd_radicado_tenant_fecha
  on gd.radicado(tenant_id, fecha_radicacion desc);
create index if not exists ix_gd_radicado_tercero
  on gd.radicado(tercero_id) where tercero_id is not null;
create index if not exists ix_gd_radicado_estado
  on gd.radicado(tenant_id, estado);
create index if not exists ix_gd_radicado_dependencia_destino
  on gd.radicado(dependencia_destino_id) where dependencia_destino_id is not null;
create index if not exists ix_gd_radicado_canal
  on gd.radicado(canal_id);
-- Full-text para asunto.
create index if not exists ix_gd_radicado_busqueda_asunto
  on gd.radicado using gin (to_tsvector('spanish', asunto || ' ' || coalesce(descripcion, '')));

alter table gd.radicado enable row level security;

drop policy if exists radicado_tenant_isolation on gd.radicado;
create policy radicado_tenant_isolation on gd.radicado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_radicado_updated_at
  before update on gd.radicado
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado SIEMPRE (Mandato #2: radicado inmutable).
create or replace function gd.radicado_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.radicado no admite DELETE — número de radicado es inmutable (RNF-011). Use anulación.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_radicado_no_delete on gd.radicado;
create trigger trg_gd_radicado_no_delete
  before delete on gd.radicado
  for each row execute function gd.radicado_block_delete();

-- UPDATE de numero_radicado SIEMPRE bloqueado.
create or replace function gd.radicado_block_numero_update()
returns trigger language plpgsql as $$
begin
  if old.numero_radicado is distinct from new.numero_radicado then
    raise exception 'numero_radicado es inmutable (RNF-011).'
      using errcode = '42501';
  end if;
  if old.fecha_radicacion is distinct from new.fecha_radicacion then
    raise exception 'fecha_radicacion es inmutable.'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_radicado_no_update_numero on gd.radicado;
create trigger trg_gd_radicado_no_update_numero
  before update on gd.radicado
  for each row execute function gd.radicado_block_numero_update();

comment on table gd.radicado is
  'GD-API-0024: corazón del módulo. numero_radicado y fecha_radicacion son '
  'INMUTABLES (RNF-011 — triggers bloquean UPDATE). DELETE prohibido. '
  'Para errores: anulación con flujo de aprobación (GD-API-0028). '
  'codigo_verificacion único por tenant — usado en endpoint público /gd/verificar/{codigo}.';

-- ----------------------------------------------------------------------------
-- 6.4 — GD-API-0026: gd.clasificacion_radicado (historial de clasificaciones).
-- ----------------------------------------------------------------------------
create table if not exists gd.clasificacion_radicado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  radicado_id uuid not null references gd.radicado(id) on delete restrict,
  tipo_clasificacion text not null check (tipo_clasificacion in (
    'pqrsd', 'correspondencia_externa', 'correspondencia_interna',
    'tramite', 'expediente'
  )),
  sub_tipo text,  -- ej. 'peticion' | 'queja' | 'reclamo' para pqrsd
  dependencia_destino_id uuid references gd.dependencia(id) on delete restrict,
  tipo_pqrsd_id uuid references gd.tipo_pqrsd(id) on delete restrict,
  estado text not null default 'vigente' check (estado in (
    'vigente', 'reemplazada'
  )),
  justificacion text,
  sugerencia_ia_id uuid,  -- FK a gd.resultado_ia (EP-013, no existe aún)
  fuente text not null default 'manual' check (fuente in (
    'manual', 'ia_aceptada', 'regla_automatica'
  )),
  clasificado_por_user_id uuid not null references app.users(id) on delete restrict,
  fecha_clasificacion timestamptz not null default now(),
  motivo_reclasificacion text,  -- solo en reclasificaciones
  reemplazada_por_id uuid references gd.clasificacion_radicado(id),
  created_at timestamptz not null default now()
);

create index if not exists ix_gd_clasif_radicado
  on gd.clasificacion_radicado(radicado_id, fecha_clasificacion desc);

-- Una sola clasificación vigente por radicado (índice único parcial).
create unique index if not exists ix_gd_clasif_vigente_unica
  on gd.clasificacion_radicado(radicado_id)
  where estado = 'vigente';

alter table gd.clasificacion_radicado enable row level security;

drop policy if exists clasificacion_radicado_tenant_isolation on gd.clasificacion_radicado;
create policy clasificacion_radicado_tenant_isolation on gd.clasificacion_radicado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- DELETE bloqueado.
create or replace function gd.clasificacion_radicado_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.clasificacion_radicado no admite DELETE. Use reclasificación.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_clasif_no_delete on gd.clasificacion_radicado;
create trigger trg_gd_clasif_no_delete
  before delete on gd.clasificacion_radicado
  for each row execute function gd.clasificacion_radicado_block_delete();

comment on table gd.clasificacion_radicado is
  'GD-API-0026: clasificaciones del radicado. Solo una vigente por radicado '
  '(índice único parcial). Reclasificación marca anterior como reemplazada y '
  'enlaza vía reemplazada_por_id (RNF-012).';

-- ----------------------------------------------------------------------------
-- 6.5 — GD-API-0028: gd.solicitud_anulacion.
-- ----------------------------------------------------------------------------
create table if not exists gd.solicitud_anulacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo_entidad text not null check (tipo_entidad in (
    'radicado', 'documento', 'pqrsd', 'correspondencia'
  )),
  entidad_afectada_id uuid not null,  -- polimórfico
  solicitante_user_id uuid not null references app.users(id) on delete restrict,
  motivo text not null,
  evidencia_archivo_digital_id uuid,
  decision text not null default 'pendiente' check (decision in (
    'pendiente', 'aprobada', 'rechazada'
  )),
  aprobador_user_id uuid references app.users(id) on delete restrict,
  observacion_decision text,
  fecha_solicitud timestamptz not null default now(),
  fecha_decision timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_solicitud_anulacion_pendientes
  on gd.solicitud_anulacion(tenant_id, decision)
  where decision = 'pendiente';
create index if not exists ix_gd_solicitud_anulacion_entidad
  on gd.solicitud_anulacion(tipo_entidad, entidad_afectada_id);

alter table gd.solicitud_anulacion enable row level security;

drop policy if exists solicitud_anulacion_tenant_isolation on gd.solicitud_anulacion;
create policy solicitud_anulacion_tenant_isolation on gd.solicitud_anulacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_solicitud_anulacion_updated_at
  before update on gd.solicitud_anulacion
  for each row execute function app.touch_updated_at();

comment on table gd.solicitud_anulacion is
  'GD-API-0028: flujo aprobación anulación. Separación funciones RNF-008: '
  'solicitante_user_id != aprobador_user_id (validado en Python).';

-- =============================================================================
-- 7. Bloque 6 — Buzón + Tareas + Notificaciones + Historial tercero.
-- =============================================================================
-- Tareas: GD-API-0034 (contactos_tercero ya tabla creada en bloque 5 — solo
--         CRUD en Python), GD-API-0035 (historial tercero), GD-API-0036..0039
--         (gd.tarea genérica + buzón), GD-API-0040 (gd.notificacion).
-- ----------------------------------------------------------------------------

-- 7.1 — GD-API-0036: gd.tarea (polimórfica).
-- entidad_origen_tipo ∈ {pqrsd, correspondencia, documento, radicado, generica}.
-- Asignación: asignado_a_user_id O asignado_a_dependencia_id (no ambos).
-- ----------------------------------------------------------------------------
create table if not exists gd.tarea (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo_tarea text not null check (tipo_tarea in (
    'clasificar', 'proyectar', 'revisar', 'aprobar', 'firmar',
    'responder', 'radicar', 'leer', 'generica'
  )),
  titulo text not null,
  descripcion text,
  -- Origen polimórfico
  entidad_origen_tipo text check (entidad_origen_tipo in (
    'pqrsd', 'correspondencia', 'documento', 'radicado', 'generica'
  )),
  entidad_origen_id uuid,
  -- Asignación
  asignado_a_user_id uuid references app.users(id) on delete restrict,
  asignado_a_dependencia_id uuid references gd.dependencia(id) on delete restrict,
  asignado_por_user_id uuid references app.users(id) on delete restrict,
  fecha_asignacion timestamptz not null default now(),
  fecha_limite timestamptz,
  prioridad text not null default 'normal' check (prioridad in (
    'baja', 'normal', 'alta', 'urgente'
  )),
  estado text not null default 'pendiente' check (estado in (
    'pendiente', 'en_proceso', 'devuelta', 'finalizada', 'vencida',
    'reasignada', 'anulada'
  )),
  -- Snapshots
  observaciones_devolucion text,
  observaciones_finalizacion text,
  motivo_anulacion text,
  -- Audit
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  finalizada_en timestamptz,
  finalizada_por_user_id uuid references app.users(id) on delete restrict,
  -- Restricciones
  constraint chk_tarea_asignacion check (
    asignado_a_user_id is not null or asignado_a_dependencia_id is not null
  )
);

create index if not exists ix_gd_tarea_asignado_user
  on gd.tarea(tenant_id, asignado_a_user_id, estado)
  where asignado_a_user_id is not null;

create index if not exists ix_gd_tarea_asignado_dependencia
  on gd.tarea(tenant_id, asignado_a_dependencia_id, estado)
  where asignado_a_dependencia_id is not null;

create index if not exists ix_gd_tarea_pendientes
  on gd.tarea(tenant_id, estado, fecha_limite)
  where estado in ('pendiente', 'en_proceso');

create index if not exists ix_gd_tarea_entidad_origen
  on gd.tarea(entidad_origen_tipo, entidad_origen_id)
  where entidad_origen_id is not null;

alter table gd.tarea enable row level security;

drop policy if exists tarea_tenant_isolation on gd.tarea;
create policy tarea_tenant_isolation on gd.tarea
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tarea_updated_at
  before update on gd.tarea
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: tareas se anulan, no se borran (Mandato #3).
create or replace function gd.tarea_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.tarea no admite DELETE. Use estado=anulada con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_tarea_no_delete on gd.tarea;
create trigger trg_gd_tarea_no_delete
  before delete on gd.tarea
  for each row execute function gd.tarea_block_delete();

comment on table gd.tarea is
  'GD-API-0036: tareas polimórficas. Origen ∈ {pqrsd|correspondencia|documento'
  '|radicado|generica}. Asignación a usuario O dependencia (no ambos).';

-- ----------------------------------------------------------------------------
-- 7.2 — GD-API-0037: gd.tarea_historial (snapshot por reasignación/cambio).
-- ----------------------------------------------------------------------------
create table if not exists gd.tarea_historial (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tarea_id uuid not null references gd.tarea(id) on delete restrict,
  tipo_evento text not null check (tipo_evento in (
    'creada', 'asignada', 'reasignada', 'iniciada', 'devuelta',
    'finalizada', 'escalada', 'anulada', 'vencida'
  )),
  estado_anterior text,
  estado_nuevo text,
  asignado_a_user_id_anterior uuid references app.users(id) on delete restrict,
  asignado_a_user_id_nuevo uuid references app.users(id) on delete restrict,
  asignado_a_dependencia_id_anterior uuid references gd.dependencia(id) on delete restrict,
  asignado_a_dependencia_id_nuevo uuid references gd.dependencia(id) on delete restrict,
  motivo text,
  ejecutado_por_user_id uuid not null references app.users(id) on delete restrict,
  actor_snapshot jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ix_gd_tarea_historial_tarea
  on gd.tarea_historial(tarea_id, created_at desc);

alter table gd.tarea_historial enable row level security;

drop policy if exists tarea_historial_tenant_isolation on gd.tarea_historial;
create policy tarea_historial_tenant_isolation on gd.tarea_historial
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only (RNF-009).
create or replace function gd.tarea_historial_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.tarea_historial es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_tarea_historial_no_update on gd.tarea_historial;
create trigger trg_gd_tarea_historial_no_update
  before update on gd.tarea_historial
  for each row execute function gd.tarea_historial_block_mutations();

drop trigger if exists trg_gd_tarea_historial_no_delete on gd.tarea_historial;
create trigger trg_gd_tarea_historial_no_delete
  before delete on gd.tarea_historial
  for each row execute function gd.tarea_historial_block_mutations();

-- ----------------------------------------------------------------------------
-- 7.3 — GD-API-0040: gd.notificacion (in-app + correo).
-- ----------------------------------------------------------------------------
create table if not exists gd.notificacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  destinatario_user_id uuid not null references app.users(id) on delete restrict,
  tipo_notificacion text not null,  -- ej. 'tarea_asignada', 'pqrsd_proxima_vencer'
  titulo text not null,
  mensaje text not null,
  -- Origen polimórfico opcional
  entidad_origen_tipo text,
  entidad_origen_id uuid,
  -- Canales
  enviada_por_canal text[] not null default array[]::text[],  -- 'in_app', 'correo', 'webhook'
  -- Estado
  leida boolean not null default false,
  fecha_lectura timestamptz,
  -- Metadata
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_notificacion_destinatario
  on gd.notificacion(tenant_id, destinatario_user_id, leida, created_at desc);

create index if not exists ix_gd_notificacion_no_leidas
  on gd.notificacion(destinatario_user_id, tenant_id)
  where leida = false;

alter table gd.notificacion enable row level security;

drop policy if exists notificacion_tenant_isolation on gd.notificacion;
create policy notificacion_tenant_isolation on gd.notificacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_notificacion_updated_at
  before update on gd.notificacion
  for each row execute function app.touch_updated_at();

comment on table gd.notificacion is
  'GD-API-0040: notificaciones por usuario. Workers reactivos a eventos de '
  'dominio crean notificaciones automáticamente (worker no implementado en '
  'bloque 6 — endpoints CRUD listos para producción).';

-- ----------------------------------------------------------------------------
-- 7.4 — GD-API-0040: gd.notificacion_preferencia (por usuario, por tipo).
-- ----------------------------------------------------------------------------
create table if not exists gd.notificacion_preferencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,
  tipo_notificacion text not null,  -- match con gd.notificacion.tipo_notificacion
  in_app_habilitado boolean not null default true,
  correo_habilitado boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, user_id, tipo_notificacion)
);

alter table gd.notificacion_preferencia enable row level security;

drop policy if exists notif_pref_tenant_isolation on gd.notificacion_preferencia;
create policy notif_pref_tenant_isolation on gd.notificacion_preferencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_notif_pref_updated_at
  before update on gd.notificacion_preferencia
  for each row execute function app.touch_updated_at();

-- =============================================================================
-- 8. Bloque 7 — EP-007 PQRSD ciclo inicial.
-- =============================================================================
-- Tareas: GD-API-0041 (alertas), GD-API-0042 (suspensión término PQRSD),
--         GD-API-0043 (PQRSD desde radicado clasificado), GD-API-0044
--         (asignación), GD-API-0045 (reasignación), GD-API-0046 (proyectar
--         respuesta).
-- ----------------------------------------------------------------------------

-- 8.1 — GD-API-0041: gd.alerta (críticas con escalado).
create table if not exists gd.alerta (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  destinatario_user_id uuid references app.users(id) on delete restrict,
  destinatario_dependencia_id uuid references gd.dependencia(id) on delete restrict,
  tipo_alerta text not null check (tipo_alerta in (
    'proximo_vencimiento', 'vencido', 'sin_asignar',
    'riesgo', 'seguridad', 'fallo_periferico', 'auto_proteccion'
  )),
  severidad text not null default 'media' check (severidad in (
    'informativa', 'media', 'alta', 'critica'
  )),
  titulo text not null,
  mensaje text not null,
  entidad_relacionada_tipo text,
  entidad_relacionada_id uuid,
  estado text not null default 'activa' check (estado in (
    'activa', 'leida', 'gestionada', 'escalada', 'cerrada'
  )),
  escalada_a_user_id uuid references app.users(id) on delete restrict,
  fecha_escalado timestamptz,
  motivo_escalado text,
  fecha_gestion timestamptz,
  gestionada_por_user_id uuid references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_alerta_destinatario check (
    destinatario_user_id is not null or destinatario_dependencia_id is not null
  )
);

create index if not exists ix_gd_alerta_destinatario_user
  on gd.alerta(tenant_id, destinatario_user_id, estado, severidad)
  where destinatario_user_id is not null;
create index if not exists ix_gd_alerta_activas
  on gd.alerta(tenant_id, estado, severidad)
  where estado = 'activa';
create index if not exists ix_gd_alerta_entidad
  on gd.alerta(entidad_relacionada_tipo, entidad_relacionada_id)
  where entidad_relacionada_id is not null;

alter table gd.alerta enable row level security;

drop policy if exists alerta_tenant_isolation on gd.alerta;
create policy alerta_tenant_isolation on gd.alerta
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_alerta_updated_at
  before update on gd.alerta
  for each row execute function app.touch_updated_at();

comment on table gd.alerta is
  'GD-API-0041: alertas críticas con escalado. Distintas de gd.notificacion '
  '(informativa). Workers programados emiten próximo_vencimiento/vencido.';

-- ----------------------------------------------------------------------------
-- 8.2 — GD-API-0043: gd.pqrsd (corazón del módulo PQRSD).
-- ----------------------------------------------------------------------------
create table if not exists gd.pqrsd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  radicado_entrada_id uuid not null references gd.radicado(id) on delete restrict,
  tipo_pqrsd_id uuid references gd.tipo_pqrsd(id) on delete restrict,
  tercero_id uuid references gd.tercero(id) on delete restrict,
  asunto text not null,
  descripcion text,
  dependencia_responsable_id uuid references gd.dependencia(id) on delete restrict,
  usuario_responsable_id uuid references app.users(id) on delete restrict,
  fecha_recepcion timestamptz not null default now(),
  fecha_limite_respuesta timestamptz,
  estado text not null default 'nueva' check (estado in (
    'nueva', 'clasificada', 'asignada', 'en_analisis', 'en_revision',
    'devuelta', 'aprobada', 'firmada', 'enviada', 'cerrada',
    'vencida', 'anulada'
  )),
  prioridad text not null default 'normal' check (prioridad in (
    'baja', 'normal', 'alta', 'urgente'
  )),
  reserva boolean not null default false,  -- info reservada/sensible
  motivo_reserva text,
  -- Cierre
  cerrada_en timestamptz,
  cerrada_por_user_id uuid references app.users(id) on delete restrict,
  motivo_cierre text,
  -- Reapertura
  reabierta_en timestamptz,
  reabierta_por_user_id uuid references app.users(id) on delete restrict,
  motivo_reapertura text,
  -- Anulación
  anulada_en timestamptz,
  anulada_por_user_id uuid references app.users(id) on delete restrict,
  motivo_anulacion text,
  -- Metadata
  actor_snapshot jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  -- Timestamps
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, radicado_entrada_id)  -- una PQRSD por radicado de entrada
);

create index if not exists ix_gd_pqrsd_tenant_estado
  on gd.pqrsd(tenant_id, estado, fecha_limite_respuesta);
create index if not exists ix_gd_pqrsd_dependencia
  on gd.pqrsd(dependencia_responsable_id, estado)
  where dependencia_responsable_id is not null;
create index if not exists ix_gd_pqrsd_responsable
  on gd.pqrsd(usuario_responsable_id, estado)
  where usuario_responsable_id is not null;
create index if not exists ix_gd_pqrsd_proximas_vencer
  on gd.pqrsd(tenant_id, fecha_limite_respuesta)
  where estado in ('nueva', 'asignada', 'en_analisis', 'en_revision');
create index if not exists ix_gd_pqrsd_tercero
  on gd.pqrsd(tercero_id) where tercero_id is not null;

alter table gd.pqrsd enable row level security;

drop policy if exists pqrsd_tenant_isolation on gd.pqrsd;
create policy pqrsd_tenant_isolation on gd.pqrsd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_pqrsd_updated_at
  before update on gd.pqrsd
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: PQRSD se anula, no se borra (Mandato #3).
create or replace function gd.pqrsd_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.pqrsd no admite DELETE. Use anulación con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_pqrsd_no_delete on gd.pqrsd;
create trigger trg_gd_pqrsd_no_delete
  before delete on gd.pqrsd
  for each row execute function gd.pqrsd_block_delete();

comment on table gd.pqrsd is
  'GD-API-0043: PQRSD creada automáticamente al clasificar radicado como '
  'tipo=pqrsd. Una por radicado (unique). fecha_limite_respuesta se calcula '
  'usando gd.calcular_fecha_limite() según tipo_pqrsd.termino_dias.';

-- ----------------------------------------------------------------------------
-- 8.3 — GD-API-0044/0045: gd.asignacion_pqrsd (historial).
-- ----------------------------------------------------------------------------
create table if not exists gd.asignacion_pqrsd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  pqrsd_id uuid not null references gd.pqrsd(id) on delete restrict,
  dependencia_id uuid references gd.dependencia(id) on delete restrict,
  usuario_asignado_id uuid references app.users(id) on delete restrict,
  asignado_por_user_id uuid references app.users(id) on delete restrict,
  fecha_asignacion timestamptz not null default now(),
  fecha_fin timestamptz,
  motivo text,
  motivo_cierre text,
  estado text not null default 'activa' check (estado in (
    'activa', 'cerrada', 'reasignada'
  )),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_asignacion_pqrsd check (
    dependencia_id is not null or usuario_asignado_id is not null
  )
);

create index if not exists ix_gd_asignacion_pqrsd_pqrsd
  on gd.asignacion_pqrsd(pqrsd_id, estado, fecha_asignacion desc);
create unique index if not exists ix_gd_asignacion_pqrsd_vigente
  on gd.asignacion_pqrsd(pqrsd_id)
  where estado = 'activa';
create index if not exists ix_gd_asignacion_pqrsd_usuario
  on gd.asignacion_pqrsd(usuario_asignado_id, estado)
  where usuario_asignado_id is not null and estado = 'activa';

alter table gd.asignacion_pqrsd enable row level security;

drop policy if exists asignacion_pqrsd_tenant_isolation on gd.asignacion_pqrsd;
create policy asignacion_pqrsd_tenant_isolation on gd.asignacion_pqrsd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_asignacion_pqrsd_updated_at
  before update on gd.asignacion_pqrsd
  for each row execute function app.touch_updated_at();

-- ----------------------------------------------------------------------------
-- 8.4 — GD-API-0046: gd.respuesta_pqrsd (workflow proyectar→firmar→radicar).
-- ----------------------------------------------------------------------------
create table if not exists gd.respuesta_pqrsd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  pqrsd_id uuid not null references gd.pqrsd(id) on delete restrict,
  -- FK a gd.documento diferida a EP-009 (sin FK formal por ahora).
  documento_id uuid,
  plantilla_id uuid,  -- FK a gd.plantilla diferida a EP-010
  contenido_borrador text,
  -- Workflow snapshots
  usuario_proyecta_id uuid not null references app.users(id) on delete restrict,
  usuario_revisa_id uuid references app.users(id) on delete restrict,
  usuario_aprueba_id uuid references app.users(id) on delete restrict,
  usuario_firma_id uuid references app.users(id) on delete restrict,
  -- Radicado de salida generado al radicar (FK válida)
  radicado_salida_id uuid references gd.radicado(id) on delete restrict,
  -- Estados workflow
  estado text not null default 'borrador' check (estado in (
    'borrador', 'en_revision', 'devuelta', 'aprobada',
    'firmada', 'radicada', 'enviada'
  )),
  -- Timestamps por fase
  fecha_proyeccion timestamptz not null default now(),
  fecha_revision timestamptz,
  fecha_aprobacion timestamptz,
  fecha_firma timestamptz,
  fecha_radicacion timestamptz,
  fecha_envio timestamptz,
  observaciones_devolucion text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_respuesta_pqrsd
  on gd.respuesta_pqrsd(pqrsd_id, estado, fecha_proyeccion desc);

alter table gd.respuesta_pqrsd enable row level security;

drop policy if exists respuesta_pqrsd_tenant_isolation on gd.respuesta_pqrsd;
create policy respuesta_pqrsd_tenant_isolation on gd.respuesta_pqrsd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_respuesta_pqrsd_updated_at
  before update on gd.respuesta_pqrsd
  for each row execute function app.touch_updated_at();

comment on table gd.respuesta_pqrsd is
  'GD-API-0046+: workflow proyectar→revisar→aprobar→firmar→radicar→enviar. '
  'RNF-008 separación funciones validada en Python (proyecta ≠ aprueba ≠ '
  'firma).';

-- ----------------------------------------------------------------------------
-- 8.5 — GD-API-0042: gd.evento_termino_pqrsd (suspensiones formales).
-- ----------------------------------------------------------------------------
create table if not exists gd.evento_termino_pqrsd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  pqrsd_id uuid not null references gd.pqrsd(id) on delete restrict,
  tipo_evento text not null check (tipo_evento in (
    'suspension', 'reanudacion', 'ampliacion',
    'solicitud_info_adicional', 'traslado_competencia'
  )),
  fecha_evento timestamptz not null default now(),
  motivo text not null,
  justificacion_legal text,
  dias_afectados int,
  fecha_limite_anterior timestamptz,
  fecha_limite_nueva timestamptz,
  usuario_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now()
);

create index if not exists ix_gd_evento_termino_pqrsd
  on gd.evento_termino_pqrsd(pqrsd_id, fecha_evento desc);

alter table gd.evento_termino_pqrsd enable row level security;

drop policy if exists evento_termino_tenant_isolation on gd.evento_termino_pqrsd;
create policy evento_termino_tenant_isolation on gd.evento_termino_pqrsd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only.
create or replace function gd.evento_termino_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.evento_termino_pqrsd es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_evento_termino_no_update on gd.evento_termino_pqrsd;
create trigger trg_gd_evento_termino_no_update
  before update on gd.evento_termino_pqrsd
  for each row execute function gd.evento_termino_block_mutations();

drop trigger if exists trg_gd_evento_termino_no_delete on gd.evento_termino_pqrsd;
create trigger trg_gd_evento_termino_no_delete
  before delete on gd.evento_termino_pqrsd
  for each row execute function gd.evento_termino_block_mutations();

comment on table gd.evento_termino_pqrsd is
  'GD-API-0042/0127: eventos que afectan el término de respuesta PQRSD '
  '(suspensión, reanudación, ampliación, traslado, info adicional). '
  'Append-only. Reconstruye historial completo del cálculo de plazo.';

-- =============================================================================
-- § 9 (BLOQUE 8) — EP-007 CIERRE: workflow respuesta + cierre/reapertura +
-- traslado por competencia + solicitud info adicional + dashboard agregado.
-- GD-API-0047..0051.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 9.1 — Estado 'trasladada' en gd.pqrsd y columnas para registrar traslado.
-- ----------------------------------------------------------------------------
-- El estado actual de pqrsd no incluía 'trasladada'. Lo agregamos
-- recreando el CHECK (Postgres no permite ALTER CHECK directo).
alter table gd.pqrsd drop constraint if exists pqrsd_estado_check;
alter table gd.pqrsd add constraint pqrsd_estado_check check (estado in (
  'nueva', 'clasificada', 'asignada', 'en_analisis', 'en_revision',
  'devuelta', 'aprobada', 'firmada', 'enviada', 'cerrada',
  'trasladada', 'vencida', 'anulada'
));

-- Columnas adicionales (traslado por competencia).
alter table gd.pqrsd add column if not exists trasladada_en timestamptz;
alter table gd.pqrsd add column if not exists trasladada_por_user_id uuid
  references app.users(id) on delete restrict;
alter table gd.pqrsd add column if not exists entidad_competente_destino text;
alter table gd.pqrsd add column if not exists motivo_traslado text;
alter table gd.pqrsd add column if not exists oficio_traslado_radicado_id uuid
  references gd.radicado(id) on delete restrict;

-- Índices para dashboard.
create index if not exists ix_gd_pqrsd_dashboard_estado_dep
  on gd.pqrsd(tenant_id, estado, dependencia_responsable_id);
create index if not exists ix_gd_pqrsd_dashboard_creacion
  on gd.pqrsd(tenant_id, created_at desc);

-- ----------------------------------------------------------------------------
-- 9.2 — Vista materializada-ready para dashboard (no materializada por ahora).
-- ----------------------------------------------------------------------------
create or replace view gd.v_pqrsd_dashboard_resumen as
select
  p.tenant_id,
  p.dependencia_responsable_id,
  p.estado,
  p.tipo_pqrsd_id,
  count(*)                                          as total,
  count(*) filter (where p.fecha_limite_respuesta is not null
                   and p.fecha_limite_respuesta < now()
                   and p.estado in ('nueva','asignada','en_analisis','en_revision'))
                                                    as vencidas,
  count(*) filter (where p.fecha_limite_respuesta is not null
                   and p.fecha_limite_respuesta >= now()
                   and p.fecha_limite_respuesta < now() + interval '3 days'
                   and p.estado in ('nueva','asignada','en_analisis','en_revision'))
                                                    as proximas_vencer,
  avg(extract(epoch from (coalesce(p.cerrada_en, now()) - p.fecha_recepcion))/86400)::numeric(10,2)
                                                    as dias_promedio_resolucion
from gd.pqrsd p
group by p.tenant_id, p.dependencia_responsable_id, p.estado, p.tipo_pqrsd_id;

comment on view gd.v_pqrsd_dashboard_resumen is
  'GD-API-0051: vista de agregaciones para dashboard PQRSD. Por (tenant, '
  'dependencia, estado, tipo) calcula total, vencidas, próximas a vencer '
  'y días promedio de resolución. RLS heredada de gd.pqrsd.';

-- =============================================================================
-- § 10 (BLOQUE 9) — EP-008 CORRESPONDENCIA: interna + externa recibida +
-- externa enviada + múltiples destinatarios + anulación.
-- GD-API-0052..0056.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 10.1 — gd.correspondencia (tabla principal).
-- ----------------------------------------------------------------------------
create table if not exists gd.correspondencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Tipo de correspondencia (3 sub-flujos).
  tipo text not null check (tipo in (
    'interna', 'externa_recibida', 'externa_enviada'
  )),

  -- Origen / Destino (polimórfico según tipo).
  dependencia_origen_id uuid references gd.dependencia(id) on delete restrict,
  dependencia_destino_id uuid references gd.dependencia(id) on delete restrict,
  tercero_remitente_id uuid references gd.tercero(id) on delete restrict,
  -- (destinatarios externos múltiples → gd.destinatario_correspondencia)

  -- Vínculo a radicado de entrada (externa_recibida) o salida (externa_enviada).
  radicado_entrada_id uuid references gd.radicado(id) on delete restrict,
  radicado_salida_id uuid references gd.radicado(id) on delete restrict,

  -- Documento principal (FK diferida a EP-009).
  documento_principal_id uuid,
  plantilla_id uuid,

  asunto text not null check (length(asunto) >= 2),
  contenido_borrador text,
  prioridad text not null default 'normal' check (prioridad in (
    'baja', 'normal', 'alta', 'urgente'
  )),
  requiere_respuesta boolean not null default false,
  fecha_limite_respuesta timestamptz,

  -- Workflow (estados aplican según tipo):
  --   interna:           borrador, enviada, leida, respondida, reenviada,
  --                       anulada
  --   externa_recibida:  derivada, gestionada, anulada
  --   externa_enviada:   borrador, en_revision, devuelta, aprobada, firmada,
  --                       radicada, enviada, anulada
  estado text not null default 'borrador' check (estado in (
    'borrador', 'enviada', 'leida', 'respondida', 'reenviada',
    'derivada', 'gestionada',
    'en_revision', 'devuelta', 'aprobada', 'firmada', 'radicada',
    'anulada'
  )),

  -- Workflow timestamps + snapshots de actores.
  usuario_proyecta_id uuid not null references app.users(id) on delete restrict,
  usuario_revisa_id uuid references app.users(id) on delete restrict,
  usuario_aprueba_id uuid references app.users(id) on delete restrict,
  usuario_firma_id uuid references app.users(id) on delete restrict,
  usuario_envio_id uuid references app.users(id) on delete restrict,
  fecha_envio timestamptz,
  fecha_aprobacion timestamptz,
  fecha_firma timestamptz,
  fecha_radicacion timestamptz,
  observaciones_devolucion text,

  -- Soporte de envío (URI a archivo / código de rastreo / etc.).
  canal_envio_id uuid references gd.canal(id) on delete restrict,
  soporte_envio_uri text,
  soporte_envio_codigo_rastreo text,
  fecha_registro_soporte timestamptz,

  -- Anulación (gd.solicitud_anulacion ya soporta tipo_entidad='correspondencia').
  anulada_en timestamptz,
  anulada_por_user_id uuid references app.users(id) on delete restrict,
  motivo_anulacion text,
  solicitud_anulacion_id uuid references gd.solicitud_anulacion(id) on delete restrict,

  -- Vínculo a correspondencia padre (reenviar / responder).
  correspondencia_padre_id uuid references gd.correspondencia(id) on delete restrict,

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- Reglas de coherencia por tipo (CHECKs simples; el resto se valida en Python).
  constraint chk_corresp_origen_segun_tipo check (
    case tipo
      when 'interna' then dependencia_origen_id is not null
      when 'externa_recibida' then radicado_entrada_id is not null
      when 'externa_enviada' then dependencia_origen_id is not null
      else true
    end
  )
);

create index if not exists ix_gd_corresp_tenant_tipo_estado
  on gd.correspondencia(tenant_id, tipo, estado);
create index if not exists ix_gd_corresp_dependencia_origen
  on gd.correspondencia(dependencia_origen_id, estado)
  where dependencia_origen_id is not null;
create index if not exists ix_gd_corresp_dependencia_destino
  on gd.correspondencia(dependencia_destino_id, estado)
  where dependencia_destino_id is not null;
create index if not exists ix_gd_corresp_radicado_entrada
  on gd.correspondencia(radicado_entrada_id)
  where radicado_entrada_id is not null;
create index if not exists ix_gd_corresp_padre
  on gd.correspondencia(correspondencia_padre_id)
  where correspondencia_padre_id is not null;
create index if not exists ix_gd_corresp_tercero
  on gd.correspondencia(tercero_remitente_id)
  where tercero_remitente_id is not null;

-- Una correspondencia por radicado de entrada (idempotencia hook clasificar).
create unique index if not exists ix_gd_corresp_radicado_entrada_unique
  on gd.correspondencia(tenant_id, radicado_entrada_id)
  where radicado_entrada_id is not null and tipo = 'externa_recibida';

alter table gd.correspondencia enable row level security;

drop policy if exists correspondencia_tenant_isolation on gd.correspondencia;
create policy correspondencia_tenant_isolation on gd.correspondencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_correspondencia_updated_at
  before update on gd.correspondencia
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: correspondencia se anula, no se borra.
create or replace function gd.correspondencia_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.correspondencia no admite DELETE. Use anulación con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_correspondencia_no_delete on gd.correspondencia;
create trigger trg_gd_correspondencia_no_delete
  before delete on gd.correspondencia
  for each row execute function gd.correspondencia_block_delete();

comment on table gd.correspondencia is
  'GD-API-0052..0054: correspondencia interna, externa recibida y externa '
  'enviada en una sola tabla con tipo discriminator. Workflow estados varía '
  'según tipo (validado en Python). Externa recibida auto-creada desde hook '
  'reactivo de clasificar (RadicadoClasificado).';

-- ----------------------------------------------------------------------------
-- 10.2 — gd.destinatario_correspondencia (GD-API-0055).
-- ----------------------------------------------------------------------------
create table if not exists gd.destinatario_correspondencia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  correspondencia_id uuid not null references gd.correspondencia(id) on delete restrict,

  -- Polimórfico: dependencia o tercero.
  tipo_destinatario text not null check (tipo_destinatario in (
    'dependencia', 'tercero'
  )),
  dependencia_id uuid references gd.dependencia(id) on delete restrict,
  tercero_id uuid references gd.tercero(id) on delete restrict,

  -- Tipo de copia (BCC = oculta).
  tipo_copia text not null default 'principal' check (tipo_copia in (
    'principal', 'copia', 'copia_oculta'
  )),

  -- Lectura (para interna).
  fecha_lectura timestamptz,
  leida_por_user_id uuid references app.users(id) on delete restrict,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint chk_dest_tipo check (
    (tipo_destinatario = 'dependencia' and dependencia_id is not null and tercero_id is null) or
    (tipo_destinatario = 'tercero'     and tercero_id is not null     and dependencia_id is null)
  )
);

create index if not exists ix_gd_destinatario_corresp
  on gd.destinatario_correspondencia(correspondencia_id);
create index if not exists ix_gd_destinatario_dep_pendientes
  on gd.destinatario_correspondencia(dependencia_id)
  where dependencia_id is not null and fecha_lectura is null;
create index if not exists ix_gd_destinatario_tercero
  on gd.destinatario_correspondencia(tercero_id)
  where tercero_id is not null;

alter table gd.destinatario_correspondencia enable row level security;

drop policy if exists destinatario_corresp_tenant_isolation
  on gd.destinatario_correspondencia;
create policy destinatario_corresp_tenant_isolation
  on gd.destinatario_correspondencia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_destinatario_corresp_updated_at
  before update on gd.destinatario_correspondencia
  for each row execute function app.touch_updated_at();

comment on table gd.destinatario_correspondencia is
  'GD-API-0055: destinatarios múltiples por correspondencia. Tipo_copia '
  'principal/copia/copia_oculta. Para interna soporta lectura por '
  'destinatario.';

-- =============================================================================
-- § 11 (BLOQUE 10) — EP-009 DOCUMENTOS: gd.documento + versiones + anexos +
-- descarga auditada + clasificación información sensible + anulación/reemplazo.
-- GD-API-0057..0063.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 11.1 — Placeholder de core.archivo_digital (EP-018 lo entregará).
-- Mientras tanto, los documentos almacenan un UUID libre que apunta a un
-- registro hipotético. NO se enforce FK para no acoplar la entrega.
-- ----------------------------------------------------------------------------
-- (Sin tabla local; archivo_digital_id queda como uuid sin FK con comment.)

-- ----------------------------------------------------------------------------
-- 11.2 — gd.documento (GD-API-0057, 0059, 0063).
-- ----------------------------------------------------------------------------
create table if not exists gd.documento (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Metadata institucional
  titulo text not null check (length(titulo) >= 2),
  descripcion text,

  -- Clasificación de información sensible (GD-API-0063, RNF-053).
  clasificacion_informacion text not null default 'interna' check (
    clasificacion_informacion in (
      'publica', 'interna', 'reservada', 'confidencial',
      'datos_personales', 'sensible'
    )
  ),

  -- Categoría TRD (EP-015 entregará series/sub-series; placeholder libre).
  trd_serie_codigo text,
  trd_subserie_codigo text,
  trd_tipo_documental text,

  -- Estado del documento (no es el estado del workflow de versión).
  estado text not null default 'activo' check (estado in (
    'activo', 'anulado', 'reemplazado', 'archivado'
  )),

  -- Versión vigente (apunta a gd.version_documento.id; deferida por orden).
  version_vigente_id uuid,
  numero_version_vigente int not null default 1,

  -- Anulación / reemplazo (GD-API-0062).
  anulado_en timestamptz,
  anulado_por_user_id uuid references app.users(id) on delete restrict,
  motivo_anulacion text,
  reemplazado_por_documento_id uuid references gd.documento(id) on delete restrict,

  -- Autoría / actualización
  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  actualizado_por_user_id uuid references app.users(id) on delete restrict,

  -- Metadata libre + búsqueda textual.
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_documento_tenant_estado
  on gd.documento(tenant_id, estado);
create index if not exists ix_gd_documento_clasificacion
  on gd.documento(tenant_id, clasificacion_informacion);
create index if not exists ix_gd_documento_trd
  on gd.documento(tenant_id, trd_serie_codigo, trd_subserie_codigo)
  where trd_serie_codigo is not null;
create index if not exists ix_gd_documento_titulo_trgm
  on gd.documento using gin (titulo gin_trgm_ops);

alter table gd.documento enable row level security;

drop policy if exists documento_tenant_isolation on gd.documento;
create policy documento_tenant_isolation on gd.documento
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_documento_updated_at
  before update on gd.documento
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: documento se anula.
create or replace function gd.documento_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.documento no admite DELETE. Use anulación con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_documento_no_delete on gd.documento;
create trigger trg_gd_documento_no_delete
  before delete on gd.documento
  for each row execute function gd.documento_block_delete();

comment on table gd.documento is
  'GD-API-0057+0059+0063: documento institucional. NO almacena binarios — '
  'cada version apunta a archivo_digital_id (FK diferida a core.archivo_digital '
  'que entregará EP-018). Clasificación de información sensible per RNF-053.';

-- ----------------------------------------------------------------------------
-- 11.3 — gd.version_documento (GD-API-0058 reglas + 0059 versionado).
-- ----------------------------------------------------------------------------
create table if not exists gd.version_documento (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  documento_id uuid not null references gd.documento(id) on delete restrict,

  numero_version int not null check (numero_version >= 1),

  -- FK diferida a EP-018 core.archivo_digital. Mientras tanto, UUID libre.
  archivo_digital_id uuid not null,

  -- Reglas suplementarias (GD-API-0058): validadas en Python al subir.
  mime_type text,
  tamano_bytes bigint check (tamano_bytes is null or tamano_bytes >= 0),
  hash_sha256 text,

  -- Workflow de la versión.
  estado text not null default 'borrador' check (estado in (
    'borrador', 'aprobada', 'firmada', 'publicada', 'reemplazada', 'anulada'
  )),

  -- Snapshots
  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  aprobado_por_user_id uuid references app.users(id) on delete restrict,
  firmado_por_user_id uuid references app.users(id) on delete restrict,

  observaciones text,
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, documento_id, numero_version)
);

create index if not exists ix_gd_version_documento_doc
  on gd.version_documento(documento_id, numero_version desc);
create index if not exists ix_gd_version_documento_archivo
  on gd.version_documento(archivo_digital_id);
create index if not exists ix_gd_version_documento_hash
  on gd.version_documento(tenant_id, hash_sha256)
  where hash_sha256 is not null;

alter table gd.version_documento enable row level security;

drop policy if exists version_documento_tenant_isolation on gd.version_documento;
create policy version_documento_tenant_isolation on gd.version_documento
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_version_documento_updated_at
  before update on gd.version_documento
  for each row execute function app.touch_updated_at();

-- Bloqueo DELETE: versiones aprobadas/firmadas/publicadas son inmutables.
create or replace function gd.version_documento_block_unsafe_delete()
returns trigger language plpgsql as $$
begin
  if old.estado in ('aprobada', 'firmada', 'publicada') then
    raise exception 'No se puede borrar version_documento en estado %', old.estado
      using errcode = '42501';
  end if;
  return old;
end;
$$;

drop trigger if exists trg_gd_version_documento_no_unsafe_delete on gd.version_documento;
create trigger trg_gd_version_documento_no_unsafe_delete
  before delete on gd.version_documento
  for each row execute function gd.version_documento_block_unsafe_delete();

-- FK diferida de documento.version_vigente_id → gd.version_documento.id.
alter table gd.documento
  drop constraint if exists fk_documento_version_vigente;
alter table gd.documento
  add constraint fk_documento_version_vigente
  foreign key (version_vigente_id)
  references gd.version_documento(id)
  on delete restrict
  deferrable initially deferred;

comment on table gd.version_documento is
  'GD-API-0058+0059: versiones del documento. Apunta a archivo_digital_id '
  '(EP-018). Versión aprobada/firmada NO se sobrescribe: se crea nueva '
  'versión. RNF-013 versionamiento.';

-- ----------------------------------------------------------------------------
-- 11.4 — gd.anexo (GD-API-0060) — polimórfico.
-- ----------------------------------------------------------------------------
create table if not exists gd.anexo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- FK diferida a core.archivo_digital (EP-018).
  archivo_digital_id uuid not null,

  -- Entidad relacionada (polimórfica).
  entidad_relacionada_tipo text not null check (entidad_relacionada_tipo in (
    'radicado', 'pqrsd', 'correspondencia', 'documento'
  )),
  entidad_relacionada_id uuid not null,

  -- Metadata del anexo
  titulo text check (titulo is null or length(titulo) >= 2),
  descripcion text,
  mime_type text,
  tamano_bytes bigint check (tamano_bytes is null or tamano_bytes >= 0),

  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ix_gd_anexo_entidad
  on gd.anexo(entidad_relacionada_tipo, entidad_relacionada_id);
create index if not exists ix_gd_anexo_archivo
  on gd.anexo(archivo_digital_id);

alter table gd.anexo enable row level security;

drop policy if exists anexo_tenant_isolation on gd.anexo;
create policy anexo_tenant_isolation on gd.anexo
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.anexo is
  'GD-API-0060: anexos polimórficos. Asocia un archivo_digital existente '
  'a un radicado / PQRSD / correspondencia / documento.';

-- ----------------------------------------------------------------------------
-- 11.5 — gd.descarga_log (GD-API-0061, RNF-059).
-- ----------------------------------------------------------------------------
create table if not exists gd.descarga_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- FK diferida a core.archivo_digital (EP-018).
  archivo_digital_id uuid not null,
  -- Opcional: documento + versión específica.
  documento_id uuid references gd.documento(id) on delete restrict,
  version_documento_id uuid references gd.version_documento(id) on delete restrict,
  -- O anexo / contexto polimórfico.
  contexto_tipo text check (contexto_tipo in (
    'documento', 'anexo', 'radicado', 'pqrsd', 'correspondencia'
  )),
  contexto_id uuid,

  -- Clasificación al momento de la descarga (snapshot, por si cambia luego).
  clasificacion_informacion text not null default 'interna' check (
    clasificacion_informacion in (
      'publica', 'interna', 'reservada', 'confidencial',
      'datos_personales', 'sensible'
    )
  ),

  -- Auditoría
  usuario_id uuid not null references app.users(id) on delete restrict,
  ip text,
  user_agent text,
  descargado_en timestamptz not null default now(),
  request_id uuid
);

create index if not exists ix_gd_descarga_archivo
  on gd.descarga_log(archivo_digital_id, descargado_en desc);
create index if not exists ix_gd_descarga_usuario
  on gd.descarga_log(usuario_id, descargado_en desc);
create index if not exists ix_gd_descarga_tenant_clasif
  on gd.descarga_log(tenant_id, clasificacion_informacion, descargado_en desc);

alter table gd.descarga_log enable row level security;

drop policy if exists descarga_log_tenant_isolation on gd.descarga_log;
create policy descarga_log_tenant_isolation on gd.descarga_log
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only: nunca se actualiza ni borra (es log).
create or replace function gd.descarga_log_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.descarga_log es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_descarga_no_update on gd.descarga_log;
create trigger trg_gd_descarga_no_update
  before update on gd.descarga_log
  for each row execute function gd.descarga_log_block_mutations();

drop trigger if exists trg_gd_descarga_no_delete on gd.descarga_log;
create trigger trg_gd_descarga_no_delete
  before delete on gd.descarga_log
  for each row execute function gd.descarga_log_block_mutations();

comment on table gd.descarga_log is
  'GD-API-0061: log de descargas. Append-only. La criticidad del evento '
  'se calcula a partir de clasificacion_informacion (reservada/confidencial '
  '→ ALTA). Snapshot de la clasificación, IP, user_agent, request_id.';

-- ----------------------------------------------------------------------------
-- 11.6 — gd.documento_entidad_relacionada (asociaciones polimórficas
-- documento → radicado | pqrsd | correspondencia | expediente).
-- ----------------------------------------------------------------------------
create table if not exists gd.documento_entidad_relacionada (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  documento_id uuid not null references gd.documento(id) on delete restrict,

  entidad_tipo text not null check (entidad_tipo in (
    'radicado', 'pqrsd', 'correspondencia', 'expediente'
  )),
  entidad_id uuid not null,
  rol text,  -- 'principal', 'evidencia', 'anexo', 'plantilla_fuente', etc.

  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),

  unique (documento_id, entidad_tipo, entidad_id, rol)
);

create index if not exists ix_gd_doc_rel_entidad
  on gd.documento_entidad_relacionada(entidad_tipo, entidad_id);

alter table gd.documento_entidad_relacionada enable row level security;

drop policy if exists doc_rel_tenant_isolation on gd.documento_entidad_relacionada;
create policy doc_rel_tenant_isolation on gd.documento_entidad_relacionada
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.documento_entidad_relacionada is
  'Asociaciones N:M entre gd.documento y entidades del dominio (radicado, '
  'pqrsd, correspondencia, expediente). Un documento puede ser principal '
  'de un radicado y al mismo tiempo evidencia de otra PQRSD.';

-- =============================================================================
-- § 12 (BLOQUE 11) — EP-010 PLANTILLAS DOCUMENTALES: CRUD + versionado +
-- generación + asociaciones (dep/tipo_tramite) + seed institucional.
-- GD-API-0064..0067.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 12.1 — gd.plantilla_documental (header).
-- ----------------------------------------------------------------------------
create table if not exists gd.plantilla_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  codigo text not null,  -- ej. 'OFICIO_RESPUESTA', 'MEMO_INTERNO'
  nombre text not null check (length(nombre) >= 2),
  descripcion text,

  -- Tipo conceptual de plantilla (libre, recomendado de catálogo institucional).
  tipo_plantilla text not null check (tipo_plantilla in (
    'oficio_respuesta', 'memorando_interno', 'constancia_radicacion',
    'traslado_competencia', 'solicitud_info_adicional',
    'respuesta_pqrsd', 'comunicacion_externa_salida',
    'otra'
  )),

  -- Estado: borrador → activa → inactiva.
  estado text not null default 'borrador' check (estado in (
    'borrador', 'activa', 'inactiva'
  )),

  -- Versión vigente (FK diferida; apunta a gd.version_plantilla.id).
  version_vigente_id uuid,
  numero_version_vigente int not null default 0,

  dependencia_propietaria_id uuid references gd.dependencia(id) on delete restrict,

  -- Metadata
  es_institucional boolean not null default false,  -- seed system-wide
  created_by_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, codigo)
);

create index if not exists ix_gd_plantilla_tenant_estado
  on gd.plantilla_documental(tenant_id, estado);
create index if not exists ix_gd_plantilla_tipo
  on gd.plantilla_documental(tenant_id, tipo_plantilla, estado);
create index if not exists ix_gd_plantilla_dependencia
  on gd.plantilla_documental(dependencia_propietaria_id)
  where dependencia_propietaria_id is not null;

alter table gd.plantilla_documental enable row level security;

drop policy if exists plantilla_documental_tenant_isolation on gd.plantilla_documental;
create policy plantilla_documental_tenant_isolation on gd.plantilla_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_plantilla_updated_at
  before update on gd.plantilla_documental
  for each row execute function app.touch_updated_at();

comment on table gd.plantilla_documental is
  'GD-API-0064: cabecera de plantilla documental. Activa solo una versión '
  'vigente a la vez (version_vigente_id). RNF-014, RNF-015 control de borradores.';

-- ----------------------------------------------------------------------------
-- 12.2 — gd.version_plantilla (cuerpo del template + json_schema de campos).
-- ----------------------------------------------------------------------------
create table if not exists gd.version_plantilla (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  plantilla_id uuid not null references gd.plantilla_documental(id) on delete restrict,

  numero_version int not null check (numero_version >= 1),

  -- Contenido del template (placeholder de DOCX/PDF base, soporta texto
  -- con marcadores tipo {{campo}}). Para almacenamiento binario real se
  -- delega a EP-018 vía archivo_digital_id.
  contenido_template text not null,
  archivo_digital_id uuid,  -- opcional: binario DOCX/PDF base
  mime_type text not null default 'text/plain',

  -- JSON Schema describiendo campos dinámicos que la plantilla acepta.
  json_schema_campos jsonb not null default '{"type":"object","properties":{}}'::jsonb,

  -- Workflow versión.
  estado text not null default 'borrador' check (estado in (
    'borrador', 'activa', 'reemplazada', 'descartada'
  )),

  notas text,
  created_by_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, plantilla_id, numero_version)
);

create index if not exists ix_gd_version_plantilla_pl
  on gd.version_plantilla(plantilla_id, numero_version desc);
create index if not exists ix_gd_version_plantilla_estado
  on gd.version_plantilla(plantilla_id, estado);

alter table gd.version_plantilla enable row level security;

drop policy if exists version_plantilla_tenant_isolation on gd.version_plantilla;
create policy version_plantilla_tenant_isolation on gd.version_plantilla
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_version_plantilla_updated_at
  before update on gd.version_plantilla
  for each row execute function app.touch_updated_at();

-- Bloqueo de mutaciones unsafe sobre versiones activas/reemplazadas.
create or replace function gd.version_plantilla_block_unsafe()
returns trigger language plpgsql as $$
begin
  -- Permitir UPDATE solo para cambios de estado controlados por el service.
  -- Bloquea EDIT del contenido_template una vez la versión está activa.
  if tg_op = 'UPDATE' and old.estado = 'activa'
     and (old.contenido_template is distinct from new.contenido_template
          or old.json_schema_campos is distinct from new.json_schema_campos) then
    raise exception 'No se puede editar contenido de version_plantilla activa. Cree nueva versión.'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_version_plantilla_immutable on gd.version_plantilla;
create trigger trg_gd_version_plantilla_immutable
  before update on gd.version_plantilla
  for each row execute function gd.version_plantilla_block_unsafe();

-- FK diferida de plantilla.version_vigente_id → gd.version_plantilla.id.
alter table gd.plantilla_documental
  drop constraint if exists fk_plantilla_version_vigente;
alter table gd.plantilla_documental
  add constraint fk_plantilla_version_vigente
  foreign key (version_vigente_id)
  references gd.version_plantilla(id)
  on delete restrict
  deferrable initially deferred;

comment on table gd.version_plantilla is
  'GD-API-0064: cuerpo de plantilla. contenido_template usa marcadores '
  '{{campo}} resueltos en generación. json_schema_campos describe los '
  'campos dinámicos esperados. Activa = inmutable.';

-- ----------------------------------------------------------------------------
-- 12.3 — gd.plantilla_asociacion (GD-API-0066).
-- ----------------------------------------------------------------------------
create table if not exists gd.plantilla_asociacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  plantilla_id uuid not null references gd.plantilla_documental(id) on delete restrict,

  asociacion_tipo text not null check (asociacion_tipo in (
    'dependencia', 'tipo_tramite'
  )),
  asociacion_id uuid,  -- si tipo=dependencia (FK lógica gd.dependencia)
  asociacion_codigo text,  -- si tipo=tipo_tramite (libre)

  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),

  constraint chk_plantilla_asoc_target check (
    (asociacion_tipo = 'dependencia' and asociacion_id is not null and asociacion_codigo is null) or
    (asociacion_tipo = 'tipo_tramite' and asociacion_codigo is not null and asociacion_id is null)
  )
);

create unique index if not exists ix_gd_pl_asoc_dep_unique
  on gd.plantilla_asociacion(plantilla_id, asociacion_id)
  where asociacion_tipo = 'dependencia';
create unique index if not exists ix_gd_pl_asoc_tt_unique
  on gd.plantilla_asociacion(plantilla_id, asociacion_codigo)
  where asociacion_tipo = 'tipo_tramite';
create index if not exists ix_gd_pl_asoc_lookup_dep
  on gd.plantilla_asociacion(asociacion_id, asociacion_tipo)
  where asociacion_tipo = 'dependencia';
create index if not exists ix_gd_pl_asoc_lookup_tt
  on gd.plantilla_asociacion(asociacion_codigo, asociacion_tipo)
  where asociacion_tipo = 'tipo_tramite';

alter table gd.plantilla_asociacion enable row level security;

drop policy if exists plantilla_asoc_tenant_isolation on gd.plantilla_asociacion;
create policy plantilla_asoc_tenant_isolation on gd.plantilla_asociacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.plantilla_asociacion is
  'GD-API-0066: asocia plantillas a dependencias o tipos de trámite '
  'para resolución automática al generar documento (p.ej. respuesta PQRSD '
  'sugiere plantilla `respuesta_pqrsd` automáticamente).';

-- =============================================================================
-- § 13 (BLOQUE 12) — EP-011 FIRMAS: escaneada + electrónica + digital stub +
-- rechazo + evidencia.
-- GD-API-0068..0072.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 13.1 — gd.firma_escaneada (GD-API-0068).
-- ----------------------------------------------------------------------------
create table if not exists gd.firma_escaneada (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,

  -- FK diferida a core.archivo_digital (EP-018).
  archivo_digital_id uuid not null,
  mime_type text not null default 'image/png',
  tamano_bytes bigint check (tamano_bytes is null or tamano_bytes >= 0),
  hash_sha256 text,

  -- Autorización institucional: solo aplica si entidad lo autoriza por política.
  estado text not null default 'pendiente_autorizacion' check (estado in (
    'pendiente_autorizacion', 'activa', 'revocada'
  )),
  autorizada_por_user_id uuid references app.users(id) on delete restrict,
  fecha_autorizacion timestamptz,
  motivo_revocacion text,

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- Un user puede tener varias firmas históricas; solo una activa a la vez.
  -- Validado en Python al activar.
  unique (tenant_id, user_id, archivo_digital_id)
);

create index if not exists ix_gd_firma_esc_user_estado
  on gd.firma_escaneada(tenant_id, user_id, estado);
create unique index if not exists ix_gd_firma_esc_activa_unica
  on gd.firma_escaneada(tenant_id, user_id)
  where estado = 'activa';

alter table gd.firma_escaneada enable row level security;

drop policy if exists firma_escaneada_tenant_isolation on gd.firma_escaneada;
create policy firma_escaneada_tenant_isolation on gd.firma_escaneada
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_firma_escaneada_updated_at
  before update on gd.firma_escaneada
  for each row execute function app.touch_updated_at();

comment on table gd.firma_escaneada is
  'GD-API-0068: imagen de firma escaneada del usuario en el vault de la '
  'entidad. Sólo se usa si la entidad lo autoriza por política. Una activa '
  'por usuario (índice único parcial).';

-- ----------------------------------------------------------------------------
-- 13.2 — gd.firma_documento (GD-API-0069, 0070, 0071, 0072).
-- ----------------------------------------------------------------------------
create table if not exists gd.firma_documento (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  documento_id uuid not null references gd.documento(id) on delete restrict,
  version_documento_id uuid not null references gd.version_documento(id) on delete restrict,
  firmante_user_id uuid not null references app.users(id) on delete restrict,

  -- Tipo de firma aplicada.
  tipo_firma text not null check (tipo_firma in (
    'escaneada', 'electronica', 'digital'
  )),

  -- Workflow:
  --   pendiente → consumada (firma exitosa) | rechazada (rechazada por firmante)
  --   consumada → revocada (revocación admin posterior)
  estado text not null default 'pendiente' check (estado in (
    'pendiente', 'consumada', 'rechazada', 'revocada'
  )),

  -- Firma escaneada referencia (si tipo='escaneada').
  firma_escaneada_id uuid references gd.firma_escaneada(id) on delete restrict,
  -- Provider digital opcional (si tipo='digital').
  certificado_id text,
  proveedor_firma_digital text,  -- 'digicert', 'gse-ad', 'andes-ssl', stub...

  -- Captura criptográfica (RNF-016).
  hash_archivo text not null,  -- SHA-256 del archivo_digital al momento de firmar
  hash_algoritmo text not null default 'sha256',

  -- Snapshot del firmante (rol, dependencia, cargo) congelado en el momento.
  snapshot_firmante jsonb not null default '{}'::jsonb,

  -- Auditoría
  ip text,
  user_agent text,
  fecha_firma timestamptz,  -- NULL si pendiente
  fecha_rechazo timestamptz,
  fecha_revocacion timestamptz,
  observaciones_rechazo text,
  motivo_revocacion text,

  -- Step-up auth (GD-API-0069: si sesión >5min, requiere re-auth).
  step_up_requerido boolean not null default false,
  step_up_satisfecho_en timestamptz,
  sesion_iniciada_en timestamptz,  -- timestamp de inicio de sesión del firmante

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_firma_doc_documento
  on gd.firma_documento(documento_id, estado);
create index if not exists ix_gd_firma_doc_version
  on gd.firma_documento(version_documento_id);
create index if not exists ix_gd_firma_doc_firmante
  on gd.firma_documento(firmante_user_id, estado);
create index if not exists ix_gd_firma_doc_hash
  on gd.firma_documento(tenant_id, hash_archivo);

alter table gd.firma_documento enable row level security;

drop policy if exists firma_documento_tenant_isolation on gd.firma_documento;
create policy firma_documento_tenant_isolation on gd.firma_documento
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_firma_documento_updated_at
  before update on gd.firma_documento
  for each row execute function app.touch_updated_at();

-- Trigger anti-mutación: una firma 'consumada' NO se puede modificar
-- excepto para registrar revocación (estado → revocada + motivo_revocacion).
create or replace function gd.firma_documento_block_unsafe()
returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and old.estado = 'consumada' then
    -- Permitir solo transición a 'revocada'.
    if new.estado not in ('consumada', 'revocada') then
      raise exception 'Firma consumada solo admite revocación.'
        using errcode = '42501';
    end if;
    -- Bloquear cambios en evidencia core (hash, snapshot, fechas firma).
    if old.hash_archivo is distinct from new.hash_archivo
       or old.snapshot_firmante is distinct from new.snapshot_firmante
       or old.fecha_firma is distinct from new.fecha_firma then
      raise exception 'Evidencia de firma consumada es inmutable.'
        using errcode = '42501';
    end if;
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_firma_documento_immutable on gd.firma_documento;
create trigger trg_gd_firma_documento_immutable
  before update on gd.firma_documento
  for each row execute function gd.firma_documento_block_unsafe();

-- DELETE bloqueado: la firma es evidencia legal.
create or replace function gd.firma_documento_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.firma_documento no admite DELETE. Es evidencia legal.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_firma_documento_no_delete on gd.firma_documento;
create trigger trg_gd_firma_documento_no_delete
  before delete on gd.firma_documento
  for each row execute function gd.firma_documento_block_delete();

comment on table gd.firma_documento is
  'GD-API-0069..0072: firma de documento (escaneada | electrónica | digital). '
  'Una firma consumada es inmutable (trigger). DELETE bloqueado (evidencia '
  'legal). snapshot_firmante guarda rol+dep+cargo al momento de firmar.';

-- =============================================================================
-- § 14 (BLOQUE 13) — EP-012 INTEGRACIÓN CON CORREO INSTITUCIONAL:
-- buzones IMAP/Graph/Gmail + correos importados + conversión a radicado +
-- acuse de recibido configurable.
-- GD-API-0073..0076.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 14.1 — gd.buzon_correo_institucional (GD-API-0073).
-- ----------------------------------------------------------------------------
create table if not exists gd.buzon_correo_institucional (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Identificación del buzón.
  nombre text not null check (length(nombre) >= 2),
  direccion_correo text not null check (direccion_correo ~ '^[^@]+@[^@]+\\.[^@]+$'),
  proveedor text not null check (proveedor in (
    'imap_generico', 'gmail_api', 'microsoft_graph', 'pop3'
  )),

  -- Asociación
  dependencia_id uuid references gd.dependencia(id) on delete restrict,

  -- Configuración (host/port para IMAP/POP3; client_id para Gmail/Graph).
  host text,
  port int check (port is null or port between 1 and 65535),
  usar_tls boolean not null default true,
  usuario_smtp text,
  config jsonb not null default '{}'::jsonb,  -- detalles del provider

  -- CRITICAL: credenciales NUNCA en texto plano. Solo referencia a secret vault.
  secret_vault_ref text not null,  -- e.g. 'gd/correo/buzon_<uuid>/credentials'
  -- Última lectura.
  ultima_lectura_en timestamptz,
  ultimo_message_id_visto text,

  -- Política de acuse de recibido (GD-API-0076).
  envio_acuse_recibido boolean not null default false,
  plantilla_acuse_id uuid references gd.plantilla_documental(id) on delete restrict,

  -- Estado del buzón.
  estado text not null default 'activa' check (estado in (
    'activa', 'inactiva', 'error_credenciales', 'error_red'
  )),
  ultimo_error_texto text,
  ultimo_error_en timestamptz,

  created_by_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, direccion_correo)
);

create index if not exists ix_gd_buzon_tenant_estado
  on gd.buzon_correo_institucional(tenant_id, estado);
create index if not exists ix_gd_buzon_dependencia
  on gd.buzon_correo_institucional(dependencia_id)
  where dependencia_id is not null;

alter table gd.buzon_correo_institucional enable row level security;

drop policy if exists buzon_correo_tenant_isolation on gd.buzon_correo_institucional;
create policy buzon_correo_tenant_isolation on gd.buzon_correo_institucional
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_buzon_updated_at
  before update on gd.buzon_correo_institucional
  for each row execute function app.touch_updated_at();

comment on table gd.buzon_correo_institucional is
  'GD-API-0073: configuración de buzones IMAP/Graph/Gmail/POP3. '
  'CRÍTICO: credenciales solo via secret_vault_ref. RNF-028 lectura sin '
  'auto-radicación.';

-- ----------------------------------------------------------------------------
-- 14.2 — gd.correo_importado (GD-API-0074, 0075).
-- ----------------------------------------------------------------------------
create table if not exists gd.correo_importado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  buzon_id uuid not null references gd.buzon_correo_institucional(id) on delete restrict,

  -- Identificador único del proveedor para evitar duplicados (RNF-028).
  message_id text not null,

  -- Cabeceras
  remitente_email text not null,
  remitente_nombre text,
  destinatarios_to text[] not null default '{}',
  destinatarios_cc text[] not null default '{}',
  destinatarios_bcc text[] not null default '{}',
  asunto text,

  -- Contenido (limitado por longitud — los binarios van como anexos vía
  -- core.archivo_digital de EP-018).
  cuerpo_texto text,
  cuerpo_html text,
  fecha_envio_original timestamptz,
  importado_en timestamptz not null default now(),

  -- Anexos: lista de archivo_digital_id (FK lógica a EP-018).
  anexos_archivo_ids uuid[] not null default '{}',

  -- Workflow del correo (RNF-028: humano decide).
  estado text not null default 'pendiente' check (estado in (
    'pendiente', 'convertido_radicado', 'asociado_radicado',
    'descartado', 'error_conversion'
  )),
  radicado_id uuid references gd.radicado(id) on delete restrict,
  convertido_por_user_id uuid references app.users(id) on delete restrict,
  fecha_decision timestamptz,
  motivo_descarte text,
  observaciones text,

  -- Acuse de recibido.
  acuse_enviado_en timestamptz,
  acuse_estado text check (acuse_estado is null or acuse_estado in (
    'enviado', 'error', 'no_aplica'
  )),
  acuse_error_texto text,

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  -- RNF-028: idempotencia — un mismo message_id no se importa dos veces.
  unique (tenant_id, buzon_id, message_id)
);

create index if not exists ix_gd_correo_buzon_estado
  on gd.correo_importado(buzon_id, estado, importado_en desc);
create index if not exists ix_gd_correo_remitente
  on gd.correo_importado(tenant_id, remitente_email);
create index if not exists ix_gd_correo_radicado
  on gd.correo_importado(radicado_id) where radicado_id is not null;
create index if not exists ix_gd_correo_pendientes
  on gd.correo_importado(tenant_id, buzon_id, importado_en desc)
  where estado = 'pendiente';

alter table gd.correo_importado enable row level security;

drop policy if exists correo_importado_tenant_isolation on gd.correo_importado;
create policy correo_importado_tenant_isolation on gd.correo_importado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_correo_importado_updated_at
  before update on gd.correo_importado
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: correo importado es evidencia, se descarta con motivo.
create or replace function gd.correo_importado_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.correo_importado no admite DELETE. Use descarte con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_correo_importado_no_delete on gd.correo_importado;
create trigger trg_gd_correo_importado_no_delete
  before delete on gd.correo_importado
  for each row execute function gd.correo_importado_block_delete();

comment on table gd.correo_importado is
  'GD-API-0074: correo descargado del buzón. RNF-028 idempotencia por '
  'message_id. Conversión a radicado SIEMPRE requiere validación humana '
  '(salvo regla institucional explícita).';

-- =============================================================================
-- § 15 (BLOQUE 14) — EP-013 AGENTES IA ASISTIDOS: solicitud + resultado +
-- decisión humana + trazabilidad + minimización PII.
-- GD-API-0077..0086.
-- Mandato: la IA SOLO sugiere. Toda materialización requiere endpoint humano.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 15.1 — gd.solicitud_ia (header de cada petición a un proveedor IA).
-- ----------------------------------------------------------------------------
create table if not exists gd.solicitud_ia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  tipo_asistencia text not null check (tipo_asistencia in (
    'clasificacion', 'extraccion', 'resumen', 'sugerencia_dependencia',
    'deteccion_duplicados', 'borrador_respuesta', 'sugerencia_termino'
  )),

  -- Entidad origen polimórfica.
  entidad_origen_tipo text not null check (entidad_origen_tipo in (
    'radicado', 'pqrsd', 'correspondencia', 'documento',
    'correo_importado'
  )),
  entidad_origen_id uuid not null,

  -- Estado del worker.
  estado text not null default 'pending' check (estado in (
    'pending', 'processing', 'completed', 'failed', 'cancelled'
  )),

  -- Payload original + datos redactados antes de enviar al proveedor.
  payload_original jsonb not null default '{}'::jsonb,
  datos_redactados jsonb not null default '{}'::jsonb,
  redacciones_aplicadas jsonb not null default '[]'::jsonb,

  -- Tracking
  proveedor text,  -- 'claude', 'stub', 'gpt-4', ...
  error_texto text,
  error_codigo text,

  solicitante_user_id uuid not null references app.users(id) on delete restrict,
  inicio_procesamiento_en timestamptz,
  fin_procesamiento_en timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_solicitud_ia_tenant_estado
  on gd.solicitud_ia(tenant_id, estado, created_at desc);
create index if not exists ix_gd_solicitud_ia_entidad
  on gd.solicitud_ia(entidad_origen_tipo, entidad_origen_id);
create index if not exists ix_gd_solicitud_ia_tipo
  on gd.solicitud_ia(tenant_id, tipo_asistencia, estado);

alter table gd.solicitud_ia enable row level security;

drop policy if exists solicitud_ia_tenant_isolation on gd.solicitud_ia;
create policy solicitud_ia_tenant_isolation on gd.solicitud_ia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_solicitud_ia_updated_at
  before update on gd.solicitud_ia
  for each row execute function app.touch_updated_at();

comment on table gd.solicitud_ia is
  'GD-API-0077, RNF-030: header de petición a proveedor IA. datos_redactados '
  'contiene la versión PII-minimizada enviada al proveedor (RNF-029, GD-API-0086).';

-- ----------------------------------------------------------------------------
-- 15.2 — gd.resultado_ia (append-only).
-- ----------------------------------------------------------------------------
create table if not exists gd.resultado_ia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  solicitud_id uuid not null references gd.solicitud_ia(id) on delete restrict,

  -- Contenido de la sugerencia (estructura depende de tipo_asistencia).
  contenido jsonb not null,
  confianza numeric(5,4) check (confianza is null or (confianza >= 0 and confianza <= 1)),
  explicacion text,

  -- Auditoría del provider
  modelo text,  -- e.g. 'claude-3.5-sonnet'
  tokens_input int check (tokens_input is null or tokens_input >= 0),
  tokens_output int check (tokens_output is null or tokens_output >= 0),
  timing_ms int check (timing_ms is null or timing_ms >= 0),

  created_at timestamptz not null default now()
);

create index if not exists ix_gd_resultado_ia_solicitud
  on gd.resultado_ia(solicitud_id, created_at desc);

alter table gd.resultado_ia enable row level security;

drop policy if exists resultado_ia_tenant_isolation on gd.resultado_ia;
create policy resultado_ia_tenant_isolation on gd.resultado_ia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only: una sugerencia NO se modifica ni elimina (RNF-030).
create or replace function gd.resultado_ia_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.resultado_ia es append-only (RNF-030 trazabilidad).'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_resultado_ia_no_update on gd.resultado_ia;
create trigger trg_gd_resultado_ia_no_update
  before update on gd.resultado_ia
  for each row execute function gd.resultado_ia_block_mutations();

drop trigger if exists trg_gd_resultado_ia_no_delete on gd.resultado_ia;
create trigger trg_gd_resultado_ia_no_delete
  before delete on gd.resultado_ia
  for each row execute function gd.resultado_ia_block_mutations();

comment on table gd.resultado_ia is
  'GD-API-0078..0083: sugerencia generada por el proveedor IA. '
  'Append-only. La estructura de `contenido` varía según tipo_asistencia '
  '(ver schemas Pydantic).';

-- ----------------------------------------------------------------------------
-- 15.3 — gd.decision_ia (GD-API-0084: humano decide).
-- ----------------------------------------------------------------------------
create table if not exists gd.decision_ia (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  resultado_id uuid not null references gd.resultado_ia(id) on delete restrict,

  decision text not null check (decision in (
    'aceptar', 'modificar', 'rechazar'
  )),
  -- Si decision='modificar', aquí va el contenido finalmente aplicado.
  contenido_modificado jsonb,
  observaciones text,

  decided_by_user_id uuid not null references app.users(id) on delete restrict,
  decided_at timestamptz not null default now(),

  -- Si la decisión disparó un endpoint humano (clasificar, asignar...),
  -- registramos referencia para trazar la materialización.
  materializado_endpoint text,
  materializado_entidad_id uuid,

  created_at timestamptz not null default now()
);

create unique index if not exists ix_gd_decision_ia_unique
  on gd.decision_ia(resultado_id);
create index if not exists ix_gd_decision_ia_user
  on gd.decision_ia(decided_by_user_id, decided_at desc);

alter table gd.decision_ia enable row level security;

drop policy if exists decision_ia_tenant_isolation on gd.decision_ia;
create policy decision_ia_tenant_isolation on gd.decision_ia
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only para decisiones: una vez registrada, inmutable.
create or replace function gd.decision_ia_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.decision_ia es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_decision_ia_no_update on gd.decision_ia;
create trigger trg_gd_decision_ia_no_update
  before update on gd.decision_ia
  for each row execute function gd.decision_ia_block_mutations();

drop trigger if exists trg_gd_decision_ia_no_delete on gd.decision_ia;
create trigger trg_gd_decision_ia_no_delete
  before delete on gd.decision_ia
  for each row execute function gd.decision_ia_block_mutations();

comment on table gd.decision_ia is
  'GD-API-0084: decisión humana sobre sugerencia IA. Unique por resultado '
  '(una decisión por sugerencia). Append-only.';

-- =============================================================================
-- § 16 (BLOQUE 15) — EP-014 REPORTES E INDICADORES: registro de
-- generaciones + agregaciones (radicados, PQRSD, correspondencia,
-- cargas trabajo, uso IA, anulaciones, auditoría) + exportación auditada.
-- GD-API-0087..0094.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 16.1 — gd.reporte_generado (GD-API-0094, RNF-054).
-- ----------------------------------------------------------------------------
create table if not exists gd.reporte_generado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Tipo de reporte (uno por GD-API-008X).
  tipo_reporte text not null check (tipo_reporte in (
    'radicados', 'pqrsd', 'correspondencia',
    'cargas_trabajo', 'uso_ia', 'anulaciones_reasignaciones',
    'auditoria_consultas_sensibles'
  )),

  -- Parámetros / filtros aplicados (jsonb).
  parametros jsonb not null default '{}'::jsonb,

  -- Formato y archivo resultante.
  formato text not null check (formato in ('json', 'csv', 'excel', 'pdf')),
  -- FK diferida a core.archivo_digital (EP-018) cuando el binario se
  -- materialice. Si formato='json', el resultado va en `resumen_inline`.
  archivo_digital_id uuid,
  resumen_inline jsonb,  -- para previews + formato='json'
  numero_filas int check (numero_filas is null or numero_filas >= 0),

  -- Flag de información sensible incluida (RNF-054).
  contiene_datos_sensibles boolean not null default false,

  -- Estado del job.
  estado text not null default 'pending' check (estado in (
    'pending', 'processing', 'completed', 'failed'
  )),
  error_texto text,

  -- Auditoría.
  generado_por_user_id uuid not null references app.users(id) on delete restrict,
  ip text,
  user_agent text,
  inicio_en timestamptz not null default now(),
  fin_en timestamptz,
  duracion_ms int check (duracion_ms is null or duracion_ms >= 0),
  -- Expiración del binario / URL pre-firmada.
  expira_en timestamptz,

  created_at timestamptz not null default now()
);

create index if not exists ix_gd_reporte_tenant_tipo
  on gd.reporte_generado(tenant_id, tipo_reporte, inicio_en desc);
create index if not exists ix_gd_reporte_user
  on gd.reporte_generado(generado_por_user_id, inicio_en desc);
create index if not exists ix_gd_reporte_estado
  on gd.reporte_generado(tenant_id, estado);

alter table gd.reporte_generado enable row level security;

drop policy if exists reporte_generado_tenant_isolation on gd.reporte_generado;
create policy reporte_generado_tenant_isolation on gd.reporte_generado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only: registros de reportes son auditoría (RNF-054).
create or replace function gd.reporte_generado_block_mutations()
returns trigger language plpgsql as $$
begin
  -- Permitir UPDATE solo para cambiar estado (pending → processing → completed/failed).
  if tg_op = 'UPDATE' and (
       old.tipo_reporte is distinct from new.tipo_reporte
       or old.parametros is distinct from new.parametros
       or old.formato is distinct from new.formato
       or old.generado_por_user_id is distinct from new.generado_por_user_id
       or old.tenant_id is distinct from new.tenant_id
     ) then
    raise exception 'gd.reporte_generado solo admite UPDATE de estado/resultado, no mutaciones del request original.'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_reporte_immutable_request on gd.reporte_generado;
create trigger trg_gd_reporte_immutable_request
  before update on gd.reporte_generado
  for each row execute function gd.reporte_generado_block_mutations();

create or replace function gd.reporte_generado_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.reporte_generado no admite DELETE (registro auditable RNF-054).'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_reporte_no_delete on gd.reporte_generado;
create trigger trg_gd_reporte_no_delete
  before delete on gd.reporte_generado
  for each row execute function gd.reporte_generado_block_delete();

comment on table gd.reporte_generado is
  'GD-API-0094, RNF-054: registro de cada reporte generado. Append-only '
  'en campos del request original; solo se actualiza estado/archivo. '
  'contiene_datos_sensibles dispara criticidad ALTA en el evento de '
  'auditoría correspondiente.';

-- =============================================================================
-- § 17 (BLOQUE 16) — EP-015 TRD/TVD: versiones + series + subseries +
-- tipos documentales + asociación dependencia + clasificación documental.
-- GD-API-0095..0100.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 17.1 — gd.version_trd (cabecera de versión de TRD).
-- ----------------------------------------------------------------------------
create table if not exists gd.version_trd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  codigo text not null,  -- e.g. 'TRD-2024-v1'
  nombre text not null check (length(nombre) >= 2),
  descripcion text,

  fecha_aprobacion date,
  fecha_inicio_vigencia date,
  fecha_fin_vigencia date,

  -- Estado de la versión.
  estado text not null default 'borrador' check (estado in (
    'borrador', 'vigente', 'historica', 'archivada'
  )),

  created_by_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, codigo),
  constraint chk_vigencia_fechas check (
    fecha_fin_vigencia is null or fecha_inicio_vigencia is null
    or fecha_fin_vigencia >= fecha_inicio_vigencia
  )
);

create index if not exists ix_gd_version_trd_tenant_estado
  on gd.version_trd(tenant_id, estado);
-- Solo UNA vigente por tenant (RNF-025).
create unique index if not exists ix_gd_version_trd_vigente_unique
  on gd.version_trd(tenant_id)
  where estado = 'vigente';

alter table gd.version_trd enable row level security;

drop policy if exists version_trd_tenant_isolation on gd.version_trd;
create policy version_trd_tenant_isolation on gd.version_trd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_version_trd_updated_at
  before update on gd.version_trd
  for each row execute function app.touch_updated_at();

comment on table gd.version_trd is
  'GD-API-0095/0096: cabecera de TRD versionada. Unique parcial garantiza '
  'una sola versión vigente por tenant. RNF-024, RNF-025.';

-- ----------------------------------------------------------------------------
-- 17.2 — gd.serie_documental.
-- ----------------------------------------------------------------------------
create table if not exists gd.serie_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  version_trd_id uuid not null references gd.version_trd(id) on delete restrict,

  codigo text not null,
  nombre text not null check (length(nombre) >= 2),
  descripcion text,

  estado text not null default 'activa' check (estado in (
    'activa', 'inactiva'
  )),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, version_trd_id, codigo)
);

create index if not exists ix_gd_serie_documental
  on gd.serie_documental(version_trd_id, estado);

alter table gd.serie_documental enable row level security;

drop policy if exists serie_documental_tenant_isolation on gd.serie_documental;
create policy serie_documental_tenant_isolation on gd.serie_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_serie_documental_updated_at
  before update on gd.serie_documental
  for each row execute function app.touch_updated_at();

comment on table gd.serie_documental is
  'GD-API-0095: serie documental por versión TRD.';

-- ----------------------------------------------------------------------------
-- 17.3 — gd.subserie_documental.
-- ----------------------------------------------------------------------------
create table if not exists gd.subserie_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  serie_id uuid not null references gd.serie_documental(id) on delete restrict,

  codigo text not null,
  nombre text not null check (length(nombre) >= 2),
  descripcion text,

  -- Tiempos de retención (RNF-038).
  tiempo_archivo_gestion_anos int check (tiempo_archivo_gestion_anos is null
                                          or tiempo_archivo_gestion_anos >= 0),
  tiempo_archivo_central_anos int check (tiempo_archivo_central_anos is null
                                          or tiempo_archivo_central_anos >= 0),
  -- Disposición final.
  disposicion_final text check (disposicion_final is null
                                 or disposicion_final in (
    'conservacion_total', 'seleccion', 'eliminacion', 'reproduccion'
  )),

  estado text not null default 'activa' check (estado in (
    'activa', 'inactiva'
  )),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, serie_id, codigo)
);

create index if not exists ix_gd_subserie_serie
  on gd.subserie_documental(serie_id, estado);

alter table gd.subserie_documental enable row level security;

drop policy if exists subserie_tenant_isolation on gd.subserie_documental;
create policy subserie_tenant_isolation on gd.subserie_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_subserie_updated_at
  before update on gd.subserie_documental
  for each row execute function app.touch_updated_at();

comment on table gd.subserie_documental is
  'GD-API-0095: subserie documental con tiempos retención + disposición '
  'final (RNF-038 conservación).';

-- ----------------------------------------------------------------------------
-- 17.4 — gd.tipo_documental.
-- ----------------------------------------------------------------------------
create table if not exists gd.tipo_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  subserie_id uuid not null references gd.subserie_documental(id) on delete restrict,

  codigo text not null,
  nombre text not null check (length(nombre) >= 2),
  descripcion text,
  estado text not null default 'activo' check (estado in (
    'activo', 'inactivo'
  )),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, subserie_id, codigo)
);

create index if not exists ix_gd_tipo_documental_subserie
  on gd.tipo_documental(subserie_id, estado);

alter table gd.tipo_documental enable row level security;

drop policy if exists tipo_documental_tenant_isolation on gd.tipo_documental;
create policy tipo_documental_tenant_isolation on gd.tipo_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tipo_documental_updated_at
  before update on gd.tipo_documental
  for each row execute function app.touch_updated_at();

comment on table gd.tipo_documental is
  'GD-API-0095: tipo documental específico bajo una subserie.';

-- ----------------------------------------------------------------------------
-- 17.5 — gd.version_tvd (Tabla de Valoración Documental).
-- ----------------------------------------------------------------------------
create table if not exists gd.version_tvd (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  codigo text not null,
  nombre text not null check (length(nombre) >= 2),
  descripcion text,
  -- Asociación TRD pertinente (puede aplicar a múltiples versiones; FK opcional).
  version_trd_id uuid references gd.version_trd(id) on delete restrict,

  fecha_aprobacion date,
  fecha_inicio_vigencia date,
  fecha_fin_vigencia date,

  estado text not null default 'borrador' check (estado in (
    'borrador', 'vigente', 'historica', 'archivada'
  )),

  created_by_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, codigo)
);

create unique index if not exists ix_gd_version_tvd_vigente_unique
  on gd.version_tvd(tenant_id)
  where estado = 'vigente';

alter table gd.version_tvd enable row level security;

drop policy if exists version_tvd_tenant_isolation on gd.version_tvd;
create policy version_tvd_tenant_isolation on gd.version_tvd
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_version_tvd_updated_at
  before update on gd.version_tvd
  for each row execute function app.touch_updated_at();

comment on table gd.version_tvd is
  'GD-API-0095: TVD versionada. Vigente único por tenant.';

-- ----------------------------------------------------------------------------
-- 17.6 — gd.dependencia_codigo_documental (GD-API-0097).
-- ----------------------------------------------------------------------------
create table if not exists gd.dependencia_codigo_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  dependencia_id uuid not null references gd.dependencia(id) on delete restrict,
  version_trd_id uuid not null references gd.version_trd(id) on delete restrict,
  -- Nivel del código: serie o subserie.
  serie_id uuid references gd.serie_documental(id) on delete restrict,
  subserie_id uuid references gd.subserie_documental(id) on delete restrict,

  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),

  constraint chk_dep_cod_target check (
    serie_id is not null or subserie_id is not null
  )
);

create index if not exists ix_gd_dep_cod_dep
  on gd.dependencia_codigo_documental(dependencia_id, version_trd_id);
create unique index if not exists ix_gd_dep_cod_serie_unique
  on gd.dependencia_codigo_documental(dependencia_id, version_trd_id, serie_id)
  where serie_id is not null;
create unique index if not exists ix_gd_dep_cod_subserie_unique
  on gd.dependencia_codigo_documental(dependencia_id, version_trd_id, subserie_id)
  where subserie_id is not null;

alter table gd.dependencia_codigo_documental enable row level security;

drop policy if exists dep_cod_tenant_isolation on gd.dependencia_codigo_documental;
create policy dep_cod_tenant_isolation on gd.dependencia_codigo_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.dependencia_codigo_documental is
  'GD-API-0097: asocia dependencia ↔ código documental (serie/subserie) '
  'para sugerencias al clasificar.';

-- ----------------------------------------------------------------------------
-- 17.7 — gd.clasificacion_documental (GD-API-0098).
-- Clasifica polimórficamente radicados, documentos, pqrsd, correspondencia,
-- expedientes contra una versión TRD específica.
-- ----------------------------------------------------------------------------
create table if not exists gd.clasificacion_documental (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  entidad_tipo text not null check (entidad_tipo in (
    'radicado', 'documento', 'pqrsd', 'correspondencia', 'expediente'
  )),
  entidad_id uuid not null,

  version_trd_id uuid not null references gd.version_trd(id) on delete restrict,
  serie_id uuid references gd.serie_documental(id) on delete restrict,
  subserie_id uuid references gd.subserie_documental(id) on delete restrict,
  tipo_documental_id uuid references gd.tipo_documental(id) on delete restrict,

  justificacion text,
  -- Estado de la clasificación: vigente | reemplazada (histórica).
  estado text not null default 'vigente' check (estado in (
    'vigente', 'reemplazada'
  )),

  clasificado_por_user_id uuid not null references app.users(id) on delete restrict,
  fecha_clasificacion timestamptz not null default now(),
  -- Cuando una clasificación se reemplaza, apuntamos a la nueva.
  reemplazada_por_id uuid references gd.clasificacion_documental(id) on delete restrict,

  created_at timestamptz not null default now()
);

create index if not exists ix_gd_clasif_doc_entidad
  on gd.clasificacion_documental(entidad_tipo, entidad_id, fecha_clasificacion desc);
create index if not exists ix_gd_clasif_doc_vigente
  on gd.clasificacion_documental(entidad_tipo, entidad_id)
  where estado = 'vigente';
-- Solo UNA vigente por (entidad, tenant) — GD-API-0098.
create unique index if not exists ix_gd_clasif_doc_unica_vigente
  on gd.clasificacion_documental(tenant_id, entidad_tipo, entidad_id)
  where estado = 'vigente';
create index if not exists ix_gd_clasif_doc_serie
  on gd.clasificacion_documental(serie_id) where serie_id is not null;
create index if not exists ix_gd_clasif_doc_subserie
  on gd.clasificacion_documental(subserie_id) where subserie_id is not null;

alter table gd.clasificacion_documental enable row level security;

drop policy if exists clasif_documental_tenant_isolation on gd.clasificacion_documental;
create policy clasif_documental_tenant_isolation on gd.clasificacion_documental
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only: clasificaciones son histórico inmutable. Para "cambiar"
-- la clasificación vigente se inserta otra fila (la anterior se marca
-- como 'reemplazada' en la misma transacción).
create or replace function gd.clasificacion_documental_block_unsafe()
returns trigger language plpgsql as $$
begin
  if tg_op = 'UPDATE' and (
       old.entidad_tipo is distinct from new.entidad_tipo
       or old.entidad_id is distinct from new.entidad_id
       or old.version_trd_id is distinct from new.version_trd_id
       or old.serie_id is distinct from new.serie_id
       or old.subserie_id is distinct from new.subserie_id
       or old.tipo_documental_id is distinct from new.tipo_documental_id
       or old.clasificado_por_user_id is distinct from new.clasificado_por_user_id
       or old.fecha_clasificacion is distinct from new.fecha_clasificacion
     ) then
    raise exception 'gd.clasificacion_documental solo admite UPDATE de estado/reemplazada_por_id.'
      using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_clasif_doc_inmutable on gd.clasificacion_documental;
create trigger trg_gd_clasif_doc_inmutable
  before update on gd.clasificacion_documental
  for each row execute function gd.clasificacion_documental_block_unsafe();

drop trigger if exists trg_gd_clasif_doc_no_delete on gd.clasificacion_documental;
create or replace function gd.clasificacion_documental_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.clasificacion_documental no admite DELETE (RNF-025 histórico inmutable).'
    using errcode = '42501';
end;
$$;
create trigger trg_gd_clasif_doc_no_delete
  before delete on gd.clasificacion_documental
  for each row execute function gd.clasificacion_documental_block_delete();

comment on table gd.clasificacion_documental is
  'GD-API-0098/0099/0100: clasificación polimórfica contra TRD. Solo una '
  'vigente por entidad. Append-only (cambio = nueva fila + marcar anterior '
  'reemplazada). RNF-025 histórico inmutable.';

-- =============================================================================
-- § 18 (BLOQUE 17) — EP-016 EXPEDIENTE ELECTRÓNICO BÁSICO:
-- expedientes + asociaciones polimórficas (documentos/radicados/pqrsd/
-- correspondencia) + apertura/cierre/reapertura + consulta agregada.
-- GD-API-0101..0104.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 18.1 — gd.expediente.
-- ----------------------------------------------------------------------------
create table if not exists gd.expediente (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  codigo text not null,  -- ej. "EXP-2026-CO-00012"
  titulo text not null check (length(titulo) >= 2),
  descripcion text,

  -- Asociación organizacional y documental.
  dependencia_responsable_id uuid references gd.dependencia(id) on delete restrict,
  serie_id uuid references gd.serie_documental(id) on delete restrict,
  subserie_id uuid references gd.subserie_documental(id) on delete restrict,

  -- Estado del expediente.
  estado text not null default 'abierto' check (estado in (
    'abierto', 'cerrado', 'reabierto', 'transferido', 'anulado'
  )),

  fecha_apertura timestamptz not null default now(),
  fecha_cierre timestamptz,
  fecha_reapertura timestamptz,
  fecha_transferencia timestamptz,
  motivo_cierre text,
  motivo_reapertura text,
  motivo_transferencia text,
  destino_transferencia text,  -- placeholder fase 2

  abierto_por_user_id uuid not null references app.users(id) on delete restrict,
  cerrado_por_user_id uuid references app.users(id) on delete restrict,
  reabierto_por_user_id uuid references app.users(id) on delete restrict,

  -- Metadatos extensibles (GD-API-0104).
  metadata jsonb not null default '{}'::jsonb,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, codigo)
);

create index if not exists ix_gd_expediente_tenant_estado
  on gd.expediente(tenant_id, estado);
create index if not exists ix_gd_expediente_dep
  on gd.expediente(dependencia_responsable_id, estado);
create index if not exists ix_gd_expediente_serie
  on gd.expediente(serie_id) where serie_id is not null;
create index if not exists ix_gd_expediente_subserie
  on gd.expediente(subserie_id) where subserie_id is not null;

alter table gd.expediente enable row level security;

drop policy if exists expediente_tenant_isolation on gd.expediente;
create policy expediente_tenant_isolation on gd.expediente
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_expediente_updated_at
  before update on gd.expediente
  for each row execute function app.touch_updated_at();

-- Trigger inmutabilidad de fechas históricas: una vez registrada
-- fecha_cierre / fecha_reapertura / fecha_transferencia / fecha_apertura,
-- no pueden cambiarse.
create or replace function gd.expediente_block_fechas_immutables()
returns trigger language plpgsql as $$
begin
  if old.fecha_apertura is distinct from new.fecha_apertura then
    raise exception 'fecha_apertura es inmutable.' using errcode = '42501';
  end if;
  if old.fecha_cierre is not null
     and old.fecha_cierre is distinct from new.fecha_cierre then
    raise exception 'fecha_cierre ya registrada es inmutable.' using errcode = '42501';
  end if;
  if old.fecha_reapertura is not null
     and old.fecha_reapertura is distinct from new.fecha_reapertura then
    raise exception 'fecha_reapertura ya registrada es inmutable.' using errcode = '42501';
  end if;
  if old.fecha_transferencia is not null
     and old.fecha_transferencia is distinct from new.fecha_transferencia then
    raise exception 'fecha_transferencia ya registrada es inmutable.' using errcode = '42501';
  end if;
  return new;
end;
$$;

drop trigger if exists trg_gd_expediente_fechas_immutables on gd.expediente;
create trigger trg_gd_expediente_fechas_immutables
  before update on gd.expediente
  for each row execute function gd.expediente_block_fechas_immutables();

-- DELETE bloqueado: expedientes se anulan, no se borran (RNF-060).
create or replace function gd.expediente_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.expediente no admite DELETE. Use anulación con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_expediente_no_delete on gd.expediente;
create trigger trg_gd_expediente_no_delete
  before delete on gd.expediente
  for each row execute function gd.expediente_block_delete();

comment on table gd.expediente is
  'GD-API-0101: expediente electrónico básico. Estados: abierto → cerrado '
  '(con motivo) → reabierto. Fechas históricas inmutables. RNF-060 '
  'preparación expediente electrónico.';

-- ----------------------------------------------------------------------------
-- 18.2 — gd.expediente_item (GD-API-0102) — asociaciones polimórficas.
-- ----------------------------------------------------------------------------
create table if not exists gd.expediente_item (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  expediente_id uuid not null references gd.expediente(id) on delete restrict,

  -- Item polimórfico (documento, radicado, pqrsd, correspondencia).
  item_tipo text not null check (item_tipo in (
    'documento', 'radicado', 'pqrsd', 'correspondencia'
  )),
  item_id uuid not null,

  orden int not null default 0,

  -- Estado del vínculo (vinculado | retirado). El retiro NO borra el
  -- item original, solo el vínculo a este expediente.
  estado text not null default 'vinculado' check (estado in (
    'vinculado', 'retirado'
  )),

  vinculado_por_user_id uuid not null references app.users(id) on delete restrict,
  fecha_vinculacion timestamptz not null default now(),

  retirado_por_user_id uuid references app.users(id) on delete restrict,
  fecha_retiro timestamptz,
  motivo_retiro text,

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Solo UN vínculo vigente por (expediente, item) — evitar duplicados.
create unique index if not exists ix_gd_expediente_item_vinculado_unique
  on gd.expediente_item(expediente_id, item_tipo, item_id)
  where estado = 'vinculado';
create index if not exists ix_gd_expediente_item_item
  on gd.expediente_item(item_tipo, item_id);
create index if not exists ix_gd_expediente_item_orden
  on gd.expediente_item(expediente_id, orden, fecha_vinculacion);

alter table gd.expediente_item enable row level security;

drop policy if exists expediente_item_tenant_isolation on gd.expediente_item;
create policy expediente_item_tenant_isolation on gd.expediente_item
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_expediente_item_updated_at
  before update on gd.expediente_item
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado: vínculo se "retira" (estado='retirado'), no se borra.
create or replace function gd.expediente_item_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.expediente_item no admite DELETE. Use retiro con motivo.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_expediente_item_no_delete on gd.expediente_item;
create trigger trg_gd_expediente_item_no_delete
  before delete on gd.expediente_item
  for each row execute function gd.expediente_item_block_delete();

comment on table gd.expediente_item is
  'GD-API-0102: vínculo polimórfico expediente ↔ item (documento|radicado|'
  'pqrsd|correspondencia). Retiro = estado=retirado (no borra item). '
  'Unique vínculo vigente por (expediente,item) impide duplicados.';

-- =============================================================================
-- § 19 (BLOQUE 18) — EP-017 RPA + APIs públicas: identidades técnicas +
-- tareas RPA + webhooks salientes + rate limiting.
-- GD-API-0105..0109.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 19.1 — gd.identidad_tecnica (GD-API-0105).
-- ----------------------------------------------------------------------------
create table if not exists gd.identidad_tecnica (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  codigo text not null,  -- e.g. 'BOT_RADICADOR_01'
  nombre text not null check (length(nombre) >= 2),
  descripcion text,

  tipo text not null check (tipo in (
    'agente_ia', 'robot_rpa', 'integrador'
  )),

  -- Credencial: solo hash (bcrypt/argon2). NUNCA la API key en claro.
  api_key_hash text not null,
  api_key_prefijo text,  -- primeros 8 chars del key para identificación

  -- Scopes / permisos (jsonb con lista de PERM-* o glob '*').
  scopes jsonb not null default '[]'::jsonb,

  estado text not null default 'activa' check (estado in (
    'activa', 'revocada', 'suspendida'
  )),

  -- Rate limiting (requests por minuto). NULL = sin límite.
  rate_limit_rpm int check (rate_limit_rpm is null or rate_limit_rpm > 0),

  -- Auditoría de uso.
  ultimo_uso_en timestamptz,
  total_requests bigint not null default 0,

  -- Asociación opcional a dependencia (alcance).
  dependencia_alcance_id uuid references gd.dependencia(id) on delete restrict,

  motivo_revocacion text,
  revocada_por_user_id uuid references app.users(id) on delete restrict,
  fecha_revocacion timestamptz,

  created_by_user_id uuid not null references app.users(id) on delete restrict,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  unique (tenant_id, codigo),
  unique (api_key_hash)  -- a nivel global para evitar colisiones
);

create index if not exists ix_gd_identidad_tecnica_tenant_estado
  on gd.identidad_tecnica(tenant_id, estado);
create index if not exists ix_gd_identidad_tecnica_tipo
  on gd.identidad_tecnica(tenant_id, tipo, estado);

alter table gd.identidad_tecnica enable row level security;

drop policy if exists identidad_tecnica_tenant_isolation on gd.identidad_tecnica;
create policy identidad_tecnica_tenant_isolation on gd.identidad_tecnica
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_identidad_tecnica_updated_at
  before update on gd.identidad_tecnica
  for each row execute function app.touch_updated_at();

comment on table gd.identidad_tecnica is
  'GD-API-0105: usuarios técnicos para RPA, bots IA, integradores. '
  'API key SOLO via hash. RNF-029, RNF-031.';

-- ----------------------------------------------------------------------------
-- 19.2 — gd.tarea_rpa (GD-API-0106).
-- ----------------------------------------------------------------------------
create table if not exists gd.tarea_rpa (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Identidad técnica que ejecuta (NULL = bandeja general; cualquiera puede).
  identidad_tecnica_id uuid references gd.identidad_tecnica(id) on delete restrict,

  tipo text not null check (length(tipo) >= 2),  -- libre: 'radicar_pdf', etc.
  payload jsonb not null default '{}'::jsonb,
  prioridad text not null default 'normal' check (prioridad in (
    'baja', 'normal', 'alta', 'urgente'
  )),

  estado text not null default 'pending' check (estado in (
    'pending', 'in_progress', 'done', 'failed', 'cancelled'
  )),

  resultado jsonb,
  error_texto text,
  error_codigo text,

  -- Concurrency control: claim_token + claim_expira_en para impedir
  -- doble procesamiento.
  claim_token uuid,
  claim_expira_en timestamptz,

  created_by_user_id uuid references app.users(id) on delete restrict,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_tarea_rpa_tenant_estado
  on gd.tarea_rpa(tenant_id, estado, prioridad desc, created_at);
create index if not exists ix_gd_tarea_rpa_identidad
  on gd.tarea_rpa(identidad_tecnica_id, estado)
  where identidad_tecnica_id is not null;
create index if not exists ix_gd_tarea_rpa_tipo
  on gd.tarea_rpa(tenant_id, tipo, estado);
create index if not exists ix_gd_tarea_rpa_claim_expira
  on gd.tarea_rpa(claim_expira_en)
  where estado = 'in_progress';

alter table gd.tarea_rpa enable row level security;

drop policy if exists tarea_rpa_tenant_isolation on gd.tarea_rpa;
create policy tarea_rpa_tenant_isolation on gd.tarea_rpa
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_tarea_rpa_updated_at
  before update on gd.tarea_rpa
  for each row execute function app.touch_updated_at();

comment on table gd.tarea_rpa is
  'GD-API-0106: bandeja de trabajo para identidades técnicas. claim_token '
  'evita doble procesamiento; claim_expira_en libera la tarea si el robot '
  'no responde a tiempo.';

-- ----------------------------------------------------------------------------
-- 19.3 — gd.webhook_subscripcion (GD-API-0108).
-- ----------------------------------------------------------------------------
create table if not exists gd.webhook_subscripcion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  identidad_tecnica_id uuid not null references gd.identidad_tecnica(id) on delete restrict,

  url text not null check (url ~ '^https?://'),
  secret_hash text not null,  -- hash del HMAC shared secret
  eventos_suscritos text[] not null default '{}',  -- glob: 'PQRSD*', '*Cerrada'
  descripcion text,

  estado text not null default 'activa' check (estado in (
    'activa', 'inactiva', 'pausada'
  )),

  -- Configuración de retry exponencial.
  max_intentos int not null default 5 check (max_intentos > 0 and max_intentos <= 20),
  backoff_inicial_segundos int not null default 30 check (backoff_inicial_segundos > 0),
  backoff_max_segundos int not null default 3600 check (backoff_max_segundos > 0),

  total_eventos_entregados bigint not null default 0,
  total_eventos_fallidos bigint not null default 0,
  ultimo_evento_en timestamptz,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_webhook_sub_identidad
  on gd.webhook_subscripcion(identidad_tecnica_id, estado);
create index if not exists ix_gd_webhook_sub_tenant_estado
  on gd.webhook_subscripcion(tenant_id, estado);

alter table gd.webhook_subscripcion enable row level security;

drop policy if exists webhook_sub_tenant_isolation on gd.webhook_subscripcion;
create policy webhook_sub_tenant_isolation on gd.webhook_subscripcion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_webhook_sub_updated_at
  before update on gd.webhook_subscripcion
  for each row execute function app.touch_updated_at();

comment on table gd.webhook_subscripcion is
  'GD-API-0108: suscripción saliente de eventos. secret SOLO via hash; '
  'eventos_suscritos soporta glob (ej. "PQRSD*"). Worker entrega con '
  'retry exponencial limitado por max_intentos + backoff_max.';

-- ----------------------------------------------------------------------------
-- 19.4 — gd.webhook_delivery (intentos de entrega).
-- ----------------------------------------------------------------------------
create table if not exists gd.webhook_delivery (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  suscripcion_id uuid not null references gd.webhook_subscripcion(id) on delete restrict,

  -- Evento que dispara la entrega (sin FK estricta — auditoría puede vivir
  -- en app.audit_logs o core.evento_auditoria; guardamos sólo el id).
  evento_id uuid not null,
  tipo_evento text not null,
  payload jsonb not null default '{}'::jsonb,

  estado text not null default 'pending' check (estado in (
    'pending', 'in_progress', 'delivered', 'failed', 'expirado'
  )),
  intentos int not null default 0 check (intentos >= 0),
  http_status int,
  http_response_body text,
  ultimo_intento_en timestamptz,
  next_retry_at timestamptz,
  delivered_at timestamptz,
  error_texto text,

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_webhook_delivery_pending
  on gd.webhook_delivery(next_retry_at, estado)
  where estado in ('pending', 'failed');
create index if not exists ix_gd_webhook_delivery_sub
  on gd.webhook_delivery(suscripcion_id, created_at desc);

alter table gd.webhook_delivery enable row level security;

drop policy if exists webhook_delivery_tenant_isolation on gd.webhook_delivery;
create policy webhook_delivery_tenant_isolation on gd.webhook_delivery
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_webhook_delivery_updated_at
  before update on gd.webhook_delivery
  for each row execute function app.touch_updated_at();

comment on table gd.webhook_delivery is
  'Intentos de entrega del worker. retry exponencial controlado por '
  'gd.webhook_subscripcion.backoff_*.';

-- ----------------------------------------------------------------------------
-- 19.5 — gd.rate_limit_uso (GD-API-0109).
-- Ventana deslizante simple: una fila por (identidad, ventana_minuto).
-- ----------------------------------------------------------------------------
create table if not exists gd.rate_limit_uso (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  identidad_tecnica_id uuid not null references gd.identidad_tecnica(id) on delete restrict,
  ventana_minuto timestamptz not null,  -- truncado al minuto
  contador int not null default 0 check (contador >= 0),

  unique (identidad_tecnica_id, ventana_minuto)
);

create index if not exists ix_gd_rate_limit_ventana
  on gd.rate_limit_uso(ventana_minuto desc);

alter table gd.rate_limit_uso enable row level security;

drop policy if exists rate_limit_tenant_isolation on gd.rate_limit_uso;
create policy rate_limit_tenant_isolation on gd.rate_limit_uso
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.rate_limit_uso is
  'GD-API-0109: contador rate limit por (identidad, minuto). Tabla '
  'efímera: limpiar filas con ventana_minuto < now() - 1 hour via cron. '
  'Para volúmenes altos migrar a Redis con TTL.';

-- =============================================================================
-- § 20 (BLOQUE 19) — EP-018 SERVICIO TRANSVERSAL DE ARCHIVOS:
-- core.archivo_digital + core.extraccion_resultado +
-- core.archivo_descarga_log + retención de bytes.
-- GD-API-0110..0114.
-- Nota: estas tablas viven en core.* (NO gd.*) porque Knowledge + GD las
-- comparten. Esto cierra los placeholders archivo_digital_id que las
-- entregas anteriores dejaron.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 20.1 — core.archivo_digital (GD-API-0110).
-- ----------------------------------------------------------------------------
create table if not exists core.archivo_digital (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,

  -- Metadata del archivo.
  nombre_original text not null,
  extension text,
  mime_type text not null,
  tamano_bytes bigint not null check (tamano_bytes >= 0),

  -- Hashes para integridad + dedupe.
  hash_sha256 text not null,
  hash_md5 text,

  -- Storage.
  storage_backend text not null check (storage_backend in (
    'filesystem', 's3', 'azure_blob', 'memory'
  )),
  -- Path local o key S3. Puede ser NULL si bytes fueron purgados.
  ruta_almacenamiento text,
  -- Si está encriptado at-rest (RNF-018).
  encriptado_at_rest boolean not null default false,
  -- Reference opcional a KMS key id.
  kms_key_ref text,

  -- Propósito declarado por el caller al subir (GD-API-0110 attach_proposito).
  proposito text not null default 'general' check (proposito in (
    'general', 'knowledge', 'gd.documento', 'gd.anexo',
    'gd.constancia', 'gd.firma_imagen', 'gd.acuse_recibido',
    'gd.plantilla_base'
  )),
  -- Contexto opcional (entidad relacionada por defecto).
  contexto_entidad_tipo text,
  contexto_entidad_id uuid,

  -- Estado lifecycle.
  estado text not null default 'cargado' check (estado in (
    'cargado', 'extrayendo', 'listo', 'bloqueado', 'anulado',
    'purgado'
  )),

  -- Antivirus.
  analisis_antivirus text not null default 'pendiente' check (
    analisis_antivirus in ('pendiente', 'limpio', 'infectado', 'error')
  ),
  motor_antivirus text,
  fecha_antivirus timestamptz,
  detalle_antivirus text,

  -- Retención (RNF-038).
  retencion_politica text default 'estandar' check (
    retencion_politica is null or retencion_politica in (
      'estandar', 'conservacion_total', 'eliminacion',
      'seleccion', 'reproduccion'
    )
  ),
  fecha_elegible_purga timestamptz,
  fecha_purga_bytes timestamptz,
  motivo_purga text,

  -- Auditoría.
  cargado_por_user_id uuid not null references app.users(id) on delete restrict,
  cargado_en timestamptz not null default now(),
  ultimo_acceso_en timestamptz,
  total_descargas bigint not null default 0,

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_core_archivo_tenant_estado
  on core.archivo_digital(tenant_id, estado);
create index if not exists ix_core_archivo_hash
  on core.archivo_digital(tenant_id, hash_sha256);
create index if not exists ix_core_archivo_proposito
  on core.archivo_digital(tenant_id, proposito, estado);
create index if not exists ix_core_archivo_contexto
  on core.archivo_digital(contexto_entidad_tipo, contexto_entidad_id)
  where contexto_entidad_id is not null;
create index if not exists ix_core_archivo_purga
  on core.archivo_digital(fecha_elegible_purga, estado)
  where fecha_purga_bytes is null and ruta_almacenamiento is not null;

alter table core.archivo_digital enable row level security;

drop policy if exists archivo_digital_tenant_isolation on core.archivo_digital;
create policy archivo_digital_tenant_isolation on core.archivo_digital
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_core_archivo_updated_at
  before update on core.archivo_digital
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado (RNF-010 append-only). Para liberar bytes, use purga
-- programada (estado='purgado', ruta_almacenamiento=NULL).
create or replace function core.archivo_digital_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'core.archivo_digital no admite DELETE. Use anulación o purga programada.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_core_archivo_no_delete on core.archivo_digital;
create trigger trg_core_archivo_no_delete
  before delete on core.archivo_digital
  for each row execute function core.archivo_digital_block_delete();

comment on table core.archivo_digital is
  'GD-API-0110+0114: registro transversal de archivos compartido entre '
  'Knowledge y Gestión Documental. Metadata append-only (RNF-010); '
  'bytes purgables vía worker programado según TRD/TVD (RNF-038).';

-- ----------------------------------------------------------------------------
-- 20.2 — core.extraccion_resultado (GD-API-0111/0112).
-- ----------------------------------------------------------------------------
create table if not exists core.extraccion_resultado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  archivo_digital_id uuid not null references core.archivo_digital(id) on delete restrict,

  motor text not null,  -- 'pypdf', 'tesseract-spa-eng', 'openpyxl', etc.
  version text,

  texto_completo text,
  -- Páginas / hojas con estructura {numero, texto, confianza, bbox?, headers?, rows?}
  paginas_jsonb jsonb not null default '[]'::jsonb,

  confianza numeric(5,4) check (confianza is null or (confianza >= 0 and confianza <= 1)),

  -- Para OCR: warning si confianza < umbral.
  warning_baja_confianza boolean not null default false,
  -- Para XLSX: truncado si excede límites.
  truncado boolean not null default false,
  motivo_truncado text,

  extraido_en timestamptz not null default now(),
  duracion_ms int check (duracion_ms is null or duracion_ms >= 0),

  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

-- Unique parcial: máximo UN resultado vigente por archivo + motor
-- (re-extracción genera nueva fila, marca anterior como obsoleta via metadata).
create unique index if not exists ix_core_extraccion_archivo_motor_unique
  on core.extraccion_resultado(archivo_digital_id, motor);
create index if not exists ix_core_extraccion_archivo
  on core.extraccion_resultado(archivo_digital_id, extraido_en desc);

alter table core.extraccion_resultado enable row level security;

drop policy if exists extraccion_resultado_tenant_isolation on core.extraccion_resultado;
create policy extraccion_resultado_tenant_isolation on core.extraccion_resultado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table core.extraccion_resultado is
  'GD-API-0111/0112: texto extraído (pypdf, tesseract OCR, openpyxl). '
  'Idempotente por (archivo, motor). Consumido por Knowledge para RAG y '
  'por GD para búsqueda léxica + sugerencias IA.';

-- ----------------------------------------------------------------------------
-- 20.3 — core.archivo_descarga_log (transversal, complementa gd.descarga_log).
-- ----------------------------------------------------------------------------
create table if not exists core.archivo_descarga_log (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  archivo_digital_id uuid not null references core.archivo_digital(id) on delete restrict,

  usuario_id uuid not null references app.users(id) on delete restrict,
  identidad_tecnica_id uuid references gd.identidad_tecnica(id) on delete restrict,

  motivo text,
  ip text,
  user_agent text,
  request_id uuid,
  descargado_en timestamptz not null default now()
);

create index if not exists ix_core_descarga_archivo
  on core.archivo_descarga_log(archivo_digital_id, descargado_en desc);
create index if not exists ix_core_descarga_usuario
  on core.archivo_descarga_log(usuario_id, descargado_en desc);

alter table core.archivo_descarga_log enable row level security;

drop policy if exists archivo_descarga_log_tenant_isolation on core.archivo_descarga_log;
create policy archivo_descarga_log_tenant_isolation on core.archivo_descarga_log
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only.
create or replace function core.descarga_log_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'core.archivo_descarga_log es append-only.' using errcode = '42501';
end;
$$;

drop trigger if exists trg_core_descarga_no_update on core.archivo_descarga_log;
create trigger trg_core_descarga_no_update
  before update on core.archivo_descarga_log
  for each row execute function core.descarga_log_block_mutations();

drop trigger if exists trg_core_descarga_no_delete on core.archivo_descarga_log;
create trigger trg_core_descarga_no_delete
  before delete on core.archivo_descarga_log
  for each row execute function core.descarga_log_block_mutations();

comment on table core.archivo_descarga_log is
  'Log transversal de descargas de archivos (Knowledge + GD). '
  'Complementa gd.descarga_log que registra contexto institucional.';

-- =============================================================================
-- § 21 (BLOQUE 20) — EP-019 auditoría consulta + EP-020 utilidades:
-- catálogo eventos + verificación constancia QR + catálogo tipos doc id +
-- versionado jerárquico dependencias + radicación contingencia + hoja
-- control + índice electrónico expediente.
-- GD-API-0119, 0120, 0122..0126.
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 21.1 — core.evento_auditoria_catalogo (GD-API-0120).
-- ----------------------------------------------------------------------------
create table if not exists core.evento_auditoria_catalogo (
  id uuid primary key default gen_random_uuid(),
  tipo_evento text not null unique,
  dominio text not null check (dominio in ('app', 'knowledge', 'gd', 'core')),
  productor_modulo text,
  criticidad_default text not null check (criticidad_default in (
    'baja', 'media', 'alta', 'critica'
  )),
  rnf_cubierto text[],
  permiso_lectura text,
  descripcion text,
  campos_snapshot jsonb not null default '[]'::jsonb,
  activo boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_core_evento_catalogo_dominio
  on core.evento_auditoria_catalogo(dominio, activo);

comment on table core.evento_auditoria_catalogo is
  'GD-API-0120: catálogo formal de eventos auditados. Sin RLS (global). '
  'Cualquier tipo_evento usado en core.evento_auditoria debe declararse '
  'aquí primero como contrato — el writer lookup soft-validates.';

-- ----------------------------------------------------------------------------
-- 21.2 — gd.catalogo_tipo_documento + gd.organizacion_tipo_documento_activo
-- (GD-API-0123).
-- ----------------------------------------------------------------------------
create table if not exists gd.catalogo_tipo_documento (
  codigo text primary key,
  nombre text not null,
  pais_iso text not null check (length(pais_iso) = 2 or pais_iso = 'XX'),
  formato_regex text,
  activo_global boolean not null default true,
  created_at timestamptz not null default now()
);

-- Sin RLS — catálogo global.
comment on table gd.catalogo_tipo_documento is
  'GD-API-0123: catálogo GLOBAL de tipos de documento de identidad por '
  'país. Sin RLS — todas las organizaciones lo ven. Selección de cuáles '
  'usar es por organización en gd.organizacion_tipo_documento_activo.';

create table if not exists gd.organizacion_tipo_documento_activo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  codigo_tipo_doc text not null references gd.catalogo_tipo_documento(codigo) on delete restrict,
  activado boolean not null default true,
  es_default boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, codigo_tipo_doc)
);

-- Solo un default por tenant.
create unique index if not exists ix_gd_org_tipo_doc_default_unico
  on gd.organizacion_tipo_documento_activo(tenant_id)
  where es_default = true and activado = true;

alter table gd.organizacion_tipo_documento_activo enable row level security;

drop policy if exists org_tipo_doc_tenant_isolation
  on gd.organizacion_tipo_documento_activo;
create policy org_tipo_doc_tenant_isolation
  on gd.organizacion_tipo_documento_activo
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_org_tipo_doc_updated_at
  before update on gd.organizacion_tipo_documento_activo
  for each row execute function app.touch_updated_at();

-- Seed de tipos comunes Colombia + Latam + EUA.
insert into gd.catalogo_tipo_documento (codigo, nombre, pais_iso, formato_regex)
values
  ('CC', 'Cédula de Ciudadanía', 'CO', '^\d{6,10}$'),
  ('CE', 'Cédula de Extranjería', 'CO', '^\d{6,10}$'),
  ('NIT', 'Número de Identificación Tributaria', 'CO', '^\d{8,10}(-\d)?$'),
  ('TI', 'Tarjeta de Identidad', 'CO', '^\d{8,11}$'),
  ('RC', 'Registro Civil', 'CO', NULL),
  ('PA', 'Pasaporte', 'XX', NULL),
  ('RFC', 'Registro Federal de Contribuyentes', 'MX',
   '^[A-Z]{4}\d{6}[A-Z0-9]{3}$'),
  ('CURP', 'Clave Única de Registro de Población', 'MX',
   '^[A-Z]{4}\d{6}[HM][A-Z]{5}[A-Z0-9]\d$'),
  ('DNI', 'Documento Nacional de Identidad', 'AR', '^\d{7,8}$'),
  ('CUIT', 'Clave Única de Identificación Tributaria', 'AR',
   '^\d{2}-\d{8}-\d$'),
  ('EIN', 'Employer Identification Number', 'US', '^\d{2}-\d{7}$'),
  ('SSN', 'Social Security Number', 'US', '^\d{3}-\d{2}-\d{4}$'),
  ('ITIN', 'Individual Taxpayer Identification Number', 'US',
   '^9\d{2}-\d{2}-\d{4}$'),
  ('OTRO', 'Otro tipo de identificación', 'XX', NULL)
on conflict (codigo) do nothing;

-- ----------------------------------------------------------------------------
-- 21.3 — gd.relacion_dependencia_historica (GD-API-0124).
-- ----------------------------------------------------------------------------
create table if not exists gd.relacion_dependencia_historica (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  dependencia_id uuid not null references gd.dependencia(id) on delete restrict,
  dependencia_padre_id uuid references gd.dependencia(id) on delete restrict,
  fecha_inicio_vigencia date not null default current_date,
  fecha_fin_vigencia date,
  tipo_cambio text not null check (tipo_cambio in (
    'creacion', 'cambio_nombre', 'cambio_padre',
    'fusion_origen', 'fusion_destino',
    'division_origen', 'division_destino', 'cierre'
  )),
  motivo_cambio text,
  acto_administrativo text,
  registrado_por_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  constraint chk_relacion_fechas check (
    fecha_fin_vigencia is null or fecha_fin_vigencia >= fecha_inicio_vigencia
  )
);

create index if not exists ix_gd_relacion_dep_dep
  on gd.relacion_dependencia_historica(dependencia_id, fecha_inicio_vigencia desc);
create index if not exists ix_gd_relacion_dep_padre
  on gd.relacion_dependencia_historica(dependencia_padre_id, fecha_inicio_vigencia desc)
  where dependencia_padre_id is not null;

alter table gd.relacion_dependencia_historica enable row level security;

drop policy if exists relacion_dep_hist_tenant_isolation
  on gd.relacion_dependencia_historica;
create policy relacion_dep_hist_tenant_isolation
  on gd.relacion_dependencia_historica
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.relacion_dependencia_historica is
  'GD-API-0124: versión histórica del vínculo dependencia↔padre. Permite '
  'reconstruir jerarquía vigente a cualquier fecha pasada para trazar '
  'radicados antiguos contra estructura organizacional de la época.';

-- ----------------------------------------------------------------------------
-- 21.4 — ALTER gd.radicado: campos contingencia (GD-API-0125).
-- ----------------------------------------------------------------------------
alter table gd.radicado
  add column if not exists es_radicacion_contingencia boolean not null default false;
alter table gd.radicado
  add column if not exists fecha_radicacion_real timestamptz;
alter table gd.radicado
  add column if not exists justificacion_contingencia text;
alter table gd.radicado
  add column if not exists evidencia_contingencia_archivo_id uuid;
alter table gd.radicado
  add column if not exists reconciliado_en timestamptz;
alter table gd.radicado
  add column if not exists reconciliado_por_user_id uuid
    references app.users(id) on delete restrict;

create index if not exists ix_gd_radicado_contingencia
  on gd.radicado(tenant_id, es_radicacion_contingencia, fecha_radicacion_real desc)
  where es_radicacion_contingencia = true;

-- ----------------------------------------------------------------------------
-- 21.5 — gd.expediente_hoja_control (GD-API-0126).
-- ----------------------------------------------------------------------------
create table if not exists gd.expediente_hoja_control (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  expediente_id uuid not null references gd.expediente(id) on delete restrict,
  fecha timestamptz not null default now(),
  evento text not null check (evento in (
    'apertura', 'incorporacion_item', 'retiro_item',
    'cierre', 'reapertura', 'transferencia'
  )),
  descripcion text,
  usuario_id uuid not null references app.users(id) on delete restrict,
  snapshot_jsonb jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists ix_gd_exp_hoja_expediente
  on gd.expediente_hoja_control(expediente_id, fecha);

alter table gd.expediente_hoja_control enable row level security;

drop policy if exists exp_hoja_tenant_isolation on gd.expediente_hoja_control;
create policy exp_hoja_tenant_isolation on gd.expediente_hoja_control
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only.
create or replace function gd.exp_hoja_control_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.expediente_hoja_control es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_exp_hoja_no_update on gd.expediente_hoja_control;
create trigger trg_gd_exp_hoja_no_update
  before update on gd.expediente_hoja_control
  for each row execute function gd.exp_hoja_control_block_mutations();

drop trigger if exists trg_gd_exp_hoja_no_delete on gd.expediente_hoja_control;
create trigger trg_gd_exp_hoja_no_delete
  before delete on gd.expediente_hoja_control
  for each row execute function gd.exp_hoja_control_block_mutations();

-- ----------------------------------------------------------------------------
-- 21.6 — gd.expediente_indice_electronico (GD-API-0126 preparatorio fase 2).
-- ----------------------------------------------------------------------------
create table if not exists gd.expediente_indice_electronico (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  expediente_id uuid not null references gd.expediente(id) on delete restrict,
  version_indice int not null check (version_indice >= 1),
  generado_en timestamptz not null default now(),
  generado_por_user_id uuid not null references app.users(id) on delete restrict,
  contenido_jsonb jsonb not null default '{}'::jsonb,
  hash_sha256 text,
  unique (expediente_id, version_indice)
);

create index if not exists ix_gd_exp_indice_exp
  on gd.expediente_indice_electronico(expediente_id, generado_en desc);

alter table gd.expediente_indice_electronico enable row level security;

drop policy if exists exp_indice_tenant_isolation on gd.expediente_indice_electronico;
create policy exp_indice_tenant_isolation on gd.expediente_indice_electronico
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.expediente_indice_electronico is
  'GD-API-0126: índice electrónico del expediente. Preparado para fase 2 '
  '(Acuerdo 027 AGN). v1 lo genera vía endpoint manual; fase 2 firmará y '
  'sellará temporalmente.';

-- ----------------------------------------------------------------------------
-- 21.7 — gd.constancia_radicacion (GD-API-0122).
-- Códigos verificación públicos para verificar constancia sin login.
-- ----------------------------------------------------------------------------
create table if not exists gd.constancia_radicacion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  radicado_id uuid not null references gd.radicado(id) on delete restrict,
  codigo_verificacion text not null unique,  -- token público, ~20 chars
  qr_url_publica text,  -- URL pública para QR
  generada_por_user_id uuid not null references app.users(id) on delete restrict,
  archivo_pdf_id uuid,  -- FK lógica a core.archivo_digital
  fecha_generacion timestamptz not null default now(),
  -- Política de exposición pública.
  exposicion_publica boolean not null default true,
  unique (tenant_id, radicado_id, codigo_verificacion)
);

create index if not exists ix_gd_constancia_radicado
  on gd.constancia_radicacion(radicado_id);

alter table gd.constancia_radicacion enable row level security;

drop policy if exists constancia_tenant_isolation on gd.constancia_radicacion;
create policy constancia_tenant_isolation on gd.constancia_radicacion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

comment on table gd.constancia_radicacion is
  'GD-API-0122: códigos de verificación públicos para QR de constancia. '
  'codigo_verificacion es resolvible sin auth via /api/v1/gd/verificar/{codigo}. '
  'Solo expone datos no-personales del radicado (RNF-017).';

-- =============================================================================
-- § 22 (BLOQUE 21a) — EP-021 PERIFÉRICOS DE VENTANILLA: punto_atencion +
-- periferico + impresion_radicado + digitalizacion_documento +
-- codigo_barras_radicado + evento_periferico.
-- GD-API-0128..0135.
-- Activo solo si organizacion_modulo_activacion('ventanilla_presencial_con_perifericos').
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 22.1 — gd.punto_atencion (GD-API-0130).
-- ----------------------------------------------------------------------------
create table if not exists gd.punto_atencion (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  nombre text not null check (length(nombre) >= 2),
  direccion text,
  ciudad text,
  dependencia_responsable_id uuid references gd.dependencia(id) on delete restrict,
  estado text not null default 'activo' check (estado in (
    'activo', 'inactivo', 'cerrado'
  )),
  motivo_cierre text,
  metadata jsonb not null default '{}'::jsonb,
  creado_por_user_id uuid not null references app.users(id) on delete restrict,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_punto_atencion_tenant_estado
  on gd.punto_atencion(tenant_id, estado);
create index if not exists ix_gd_punto_atencion_dep
  on gd.punto_atencion(dependencia_responsable_id)
  where dependencia_responsable_id is not null;

alter table gd.punto_atencion enable row level security;

drop policy if exists punto_atencion_tenant_isolation on gd.punto_atencion;
create policy punto_atencion_tenant_isolation on gd.punto_atencion
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_punto_atencion_updated_at
  before update on gd.punto_atencion
  for each row execute function app.touch_updated_at();

comment on table gd.punto_atencion is
  'GD-API-0130: centro físico (sede, oficina) donde están los periféricos.';

-- ----------------------------------------------------------------------------
-- 22.2 — gd.periferico (GD-API-0129).
-- ----------------------------------------------------------------------------
create table if not exists gd.periferico (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo_periferico text not null check (tipo_periferico in (
    'impresora_etiquetas', 'impresora_termica',
    'impresora_convencional', 'escaner_plano',
    'escaner_automatico', 'lector_codigo_barras', 'otro'
  )),
  nombre text not null check (length(nombre) >= 2),
  marca text,
  modelo text,
  serial text not null,
  dependencia_id uuid references gd.dependencia(id) on delete restrict,
  punto_atencion_id uuid references gd.punto_atencion(id) on delete restrict,
  estado text not null default 'activo' check (estado in (
    'activo', 'inactivo', 'mantenimiento', 'retirado'
  )),
  motivo_cambio_estado text,
  configuracion jsonb not null default '{}'::jsonb,
  ultimo_handshake_en timestamptz,
  registrado_por_user_id uuid not null references app.users(id) on delete restrict,
  fecha_registro timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, serial)
);

create index if not exists ix_gd_periferico_tenant_estado
  on gd.periferico(tenant_id, estado, tipo_periferico);
create index if not exists ix_gd_periferico_punto
  on gd.periferico(punto_atencion_id, estado)
  where punto_atencion_id is not null;
create index if not exists ix_gd_periferico_dependencia
  on gd.periferico(dependencia_id, estado)
  where dependencia_id is not null;

alter table gd.periferico enable row level security;

drop policy if exists periferico_tenant_isolation on gd.periferico;
create policy periferico_tenant_isolation on gd.periferico
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_periferico_updated_at
  before update on gd.periferico
  for each row execute function app.touch_updated_at();

comment on table gd.periferico is
  'GD-API-0128/0129: hardware autorizado (impresora, escáner, lector). '
  'unique(tenant_id, serial) impide registrar 2 veces el mismo equipo.';

-- ----------------------------------------------------------------------------
-- 22.3 — gd.codigo_barras_radicado (GD-API-0131).
-- ----------------------------------------------------------------------------
create table if not exists gd.codigo_barras_radicado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  tipo_codigo text not null check (tipo_codigo in (
    'codigo_barras', 'qr', 'otro'
  )),
  radicado_id uuid references gd.radicado(id) on delete restrict,
  documento_id uuid references gd.documento(id) on delete restrict,
  expediente_id uuid references gd.expediente(id) on delete restrict,
  -- URL pública + token opaco. NUNCA datos sensibles.
  valor_codigo text not null,
  token_opaco text not null,  -- ~12 chars, único
  fecha_generacion timestamptz not null default now(),
  generado_por_user_id uuid not null references app.users(id) on delete restrict,
  estado text not null default 'activo' check (estado in (
    'activo', 'anulado', 'reemplazado'
  )),
  reemplazado_por_id uuid references gd.codigo_barras_radicado(id) on delete restrict,
  motivo_anulacion text,
  created_at timestamptz not null default now(),
  unique (token_opaco),
  constraint chk_codigo_barras_entidad check (
    radicado_id is not null or documento_id is not null
    or expediente_id is not null
  )
);

create index if not exists ix_gd_cb_radicado
  on gd.codigo_barras_radicado(radicado_id, estado, fecha_generacion desc)
  where radicado_id is not null;
create index if not exists ix_gd_cb_documento
  on gd.codigo_barras_radicado(documento_id) where documento_id is not null;

alter table gd.codigo_barras_radicado enable row level security;

drop policy if exists cb_radicado_tenant_isolation on gd.codigo_barras_radicado;
create policy cb_radicado_tenant_isolation on gd.codigo_barras_radicado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- DELETE bloqueado: histórico de actos oficiales.
create or replace function gd.cb_radicado_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.codigo_barras_radicado no admite DELETE.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_cb_no_delete on gd.codigo_barras_radicado;
create trigger trg_gd_cb_no_delete
  before delete on gd.codigo_barras_radicado
  for each row execute function gd.cb_radicado_block_delete();

comment on table gd.codigo_barras_radicado is
  'GD-API-0131: códigos de barras/QR generados. valor_codigo SIEMPRE es '
  'URL + token opaco. NO contiene datos personales (Doc 6 § 14).';

-- ----------------------------------------------------------------------------
-- 22.4 — gd.impresion_radicado (GD-API-0132/0133/0134).
-- ----------------------------------------------------------------------------
create table if not exists gd.impresion_radicado (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  radicado_id uuid not null references gd.radicado(id) on delete restrict,
  documento_id uuid references gd.documento(id) on delete restrict,
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  usuario_id uuid not null references app.users(id) on delete restrict,
  tipo_impresion text not null check (tipo_impresion in (
    'etiqueta_codigo_barras', 'etiqueta_qr', 'constancia_radicacion',
    'sello_documento', 'sticker', 'comprobante'
  )),
  formato text,  -- estandar/compacta/sticker
  -- Snapshot de datos impresos (NO el bitmap, los datos).
  contenido_impreso jsonb not null default '{}'::jsonb,
  archivo_digital_id uuid,  -- FK lógica a core.archivo_digital
  fecha_impresion timestamptz not null default now(),
  estado text not null default 'encolada' check (estado in (
    'encolada', 'generada', 'fallida', 'anulada', 'reemplazada'
  )),
  mensaje_error text,
  latencia_ms int check (latencia_ms is null or latencia_ms >= 0),
  motivo_reimpresion text,
  intentos_reimpresion smallint not null default 0
    check (intentos_reimpresion >= 0),
  impresion_original_id uuid references gd.impresion_radicado(id) on delete restrict,
  reportado_en timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_impresion_radicado
  on gd.impresion_radicado(radicado_id, fecha_impresion desc);
create index if not exists ix_gd_impresion_periferico
  on gd.impresion_radicado(periferico_id, estado, fecha_impresion desc);
create index if not exists ix_gd_impresion_estado
  on gd.impresion_radicado(tenant_id, estado, fecha_impresion desc);

alter table gd.impresion_radicado enable row level security;

drop policy if exists impresion_radicado_tenant_isolation on gd.impresion_radicado;
create policy impresion_radicado_tenant_isolation on gd.impresion_radicado
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_impresion_updated_at
  before update on gd.impresion_radicado
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado.
create or replace function gd.impresion_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.impresion_radicado no admite DELETE (registro histórico).'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_impresion_no_delete on gd.impresion_radicado;
create trigger trg_gd_impresion_no_delete
  before delete on gd.impresion_radicado
  for each row execute function gd.impresion_block_delete();

comment on table gd.impresion_radicado is
  'GD-API-0132/0133/0134: cada impresión (etiqueta/constancia/sticker) '
  'queda registrada. DELETE bloqueado. intentos_reimpresion crece cuando '
  'se reimprime (RFP-003: requiere aprobación si >3).';

-- ----------------------------------------------------------------------------
-- 22.5 — gd.digitalizacion_documento (GD-API-0135).
-- ----------------------------------------------------------------------------
create table if not exists gd.digitalizacion_documento (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  radicado_id uuid references gd.radicado(id) on delete restrict,
  documento_id uuid references gd.documento(id) on delete restrict,
  archivo_digital_id uuid,  -- FK lógica a core.archivo_digital
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  usuario_id uuid not null references app.users(id) on delete restrict,
  tipo_digitalizacion text not null check (tipo_digitalizacion in (
    'plano', 'automatico', 'lote', 'individual'
  )),
  numero_paginas int check (numero_paginas is null or numero_paginas >= 0),
  calidad_dpi int check (calidad_dpi is null or calidad_dpi between 50 and 4800),
  fecha_digitalizacion timestamptz not null default now(),
  estado text not null default 'encolada' check (estado in (
    'encolada', 'correcta', 'fallida', 'incompleta', 'reemplazada'
  )),
  mensaje_error text,
  observacion text,
  lote_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_digit_radicado
  on gd.digitalizacion_documento(radicado_id, fecha_digitalizacion desc)
  where radicado_id is not null;
create index if not exists ix_gd_digit_periferico
  on gd.digitalizacion_documento(periferico_id, estado, fecha_digitalizacion desc);
create index if not exists ix_gd_digit_lote
  on gd.digitalizacion_documento(lote_id, fecha_digitalizacion)
  where lote_id is not null;

alter table gd.digitalizacion_documento enable row level security;

drop policy if exists digit_tenant_isolation on gd.digitalizacion_documento;
create policy digit_tenant_isolation on gd.digitalizacion_documento
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_digit_updated_at
  before update on gd.digitalizacion_documento
  for each row execute function app.touch_updated_at();

-- DELETE bloqueado.
create or replace function gd.digit_block_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.digitalizacion_documento no admite DELETE.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_digit_no_delete on gd.digitalizacion_documento;
create trigger trg_gd_digit_no_delete
  before delete on gd.digitalizacion_documento
  for each row execute function gd.digit_block_delete();

comment on table gd.digitalizacion_documento is
  'GD-API-0135/0136: cada digitalización individual o de lote. '
  'archivo_digital_id apunta a core.archivo_digital con proposito='
  'gd.digitalizacion. Reemplaza la anterior si estado=incompleta.';

-- ----------------------------------------------------------------------------
-- 22.6 — gd.evento_periferico (GD-API-0138 telemetría — placeholder bloque 21b).
-- ----------------------------------------------------------------------------
create table if not exists gd.evento_periferico (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  usuario_id uuid references app.users(id) on delete restrict,
  tipo_evento text not null check (tipo_evento in (
    'comando_enviado', 'comando_exitoso', 'comando_fallido',
    'conexion_perdida', 'conexion_recuperada',
    'mantenimiento_iniciado', 'mantenimiento_finalizado',
    'autenticacion_fallida_agente', 'configuracion_modificada'
  )),
  entidad_relacionada_tipo text,
  entidad_relacionada_id uuid,
  resultado text check (resultado is null or resultado in (
    'exito', 'fallo', 'timeout', 'parcial'
  )),
  mensaje_error text,
  latencia_ms int check (latencia_ms is null or latencia_ms >= 0),
  fecha_hora timestamptz not null default now()
);

create index if not exists ix_gd_evento_perif_perif
  on gd.evento_periferico(periferico_id, fecha_hora desc);
create index if not exists ix_gd_evento_perif_resultado
  on gd.evento_periferico(tenant_id, resultado, fecha_hora desc);

alter table gd.evento_periferico enable row level security;

drop policy if exists evento_periferico_tenant_isolation on gd.evento_periferico;
create policy evento_periferico_tenant_isolation on gd.evento_periferico
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Append-only.
create or replace function gd.evento_periferico_block_mutations()
returns trigger language plpgsql as $$
begin
  raise exception 'gd.evento_periferico es append-only.'
    using errcode = '42501';
end;
$$;

drop trigger if exists trg_gd_evento_perif_no_update on gd.evento_periferico;
create trigger trg_gd_evento_perif_no_update
  before update on gd.evento_periferico
  for each row execute function gd.evento_periferico_block_mutations();

drop trigger if exists trg_gd_evento_perif_no_delete on gd.evento_periferico;
create trigger trg_gd_evento_perif_no_delete
  before delete on gd.evento_periferico
  for each row execute function gd.evento_periferico_block_mutations();

comment on table gd.evento_periferico is
  'GD-API-0138: telemetría de periféricos. Append-only. Alimenta dashboard '
  'de salud de hardware (bloque 21b).';

-- =============================================================================
-- Fin de bloque 21a.
-- =============================================================================

-- =============================================================================
-- § 23 — EP-021 PERIFÉRICOS parte 2 (GD-API-0136..0142) — CIERRE BACKLOG
-- =============================================================================
-- Cubre: digitalización por lote, contexto activo, mantenimiento + dashboard
-- salud, registro agente local + auth, seed permisos PERM-PER-001..012,
-- digitalización reemplazada (validación calidad).
-- =============================================================================

-- ----------------------------------------------------------------------------
-- 23.1 — gd.digitalizacion_lote (GD-API-0136).
-- ----------------------------------------------------------------------------
create table if not exists gd.digitalizacion_lote (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  usuario_id uuid not null references app.users(id) on delete restrict,
  modo_separacion text not null check (modo_separacion in (
    'por_pagina', 'por_codigo_barras', 'manual'
  )),
  radicado_id_default uuid references gd.radicado(id) on delete restrict,
  estado text not null default 'abierto' check (estado in (
    'abierto', 'finalizado', 'abandonado'
  )),
  calidad_dpi int check (calidad_dpi is null or calidad_dpi between 50 and 4800),
  observacion text,
  total_documentos int not null default 0 check (total_documentos >= 0),
  iniciado_en timestamptz not null default now(),
  finalizado_en timestamptz,
  timeout_en timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_digit_lote_periferico
  on gd.digitalizacion_lote(periferico_id, iniciado_en desc);
create index if not exists ix_gd_digit_lote_estado
  on gd.digitalizacion_lote(tenant_id, estado, iniciado_en desc);

alter table gd.digitalizacion_lote enable row level security;

drop policy if exists digit_lote_tenant_isolation on gd.digitalizacion_lote;
create policy digit_lote_tenant_isolation on gd.digitalizacion_lote
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_digit_lote_updated_at
  before update on gd.digitalizacion_lote
  for each row execute function app.touch_updated_at();

comment on table gd.digitalizacion_lote is
  'GD-API-0136: lote de digitalización con escáner automático. '
  'modo_separacion controla cómo el agente separa páginas. timeout_en '
  'permite marcar abandonado tras 30 min default.';

-- ----------------------------------------------------------------------------
-- 23.2 — gd.contexto_periferico_usuario (GD-API-0137).
-- ----------------------------------------------------------------------------
-- TTL corto (default 5 min). Unique por (user_id, periferico_id) → UPSERT.
create table if not exists gd.contexto_periferico_usuario (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  user_id uuid not null references app.users(id) on delete restrict,
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  radicado_activo_id uuid not null references gd.radicado(id) on delete restrict,
  expira_en timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, periferico_id)
);

create index if not exists ix_gd_ctx_perif_expira
  on gd.contexto_periferico_usuario(expira_en);

alter table gd.contexto_periferico_usuario enable row level security;

drop policy if exists ctx_perif_tenant_isolation on gd.contexto_periferico_usuario;
create policy ctx_perif_tenant_isolation on gd.contexto_periferico_usuario
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_ctx_perif_updated_at
  before update on gd.contexto_periferico_usuario
  for each row execute function app.touch_updated_at();

comment on table gd.contexto_periferico_usuario is
  'GD-API-0137: contexto temporal radicado-activo por (user,periférico). '
  'TTL via expira_en. Agente local lo lee al iniciar digitalización.';

-- ----------------------------------------------------------------------------
-- 23.3 — gd.mantenimiento_periferico (GD-API-0138).
-- ----------------------------------------------------------------------------
create table if not exists gd.mantenimiento_periferico (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  periferico_id uuid not null references gd.periferico(id) on delete restrict,
  tipo text not null check (tipo in ('preventivo', 'correctivo', 'auto_proteccion')),
  descripcion text not null check (length(descripcion) >= 5),
  fecha_estimada_fin date,
  iniciado_por_user_id uuid not null references app.users(id) on delete restrict,
  iniciado_en timestamptz not null default now(),
  finalizado_en timestamptz,
  observacion_final text,
  costo numeric(12, 2) check (costo is null or costo >= 0),
  repuestos jsonb,
  finalizado_por_user_id uuid references app.users(id) on delete restrict,
  estado text not null default 'en_curso' check (estado in (
    'en_curso', 'finalizado', 'cancelado'
  )),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_mant_periferico
  on gd.mantenimiento_periferico(periferico_id, iniciado_en desc);
create index if not exists ix_gd_mant_estado
  on gd.mantenimiento_periferico(tenant_id, estado);

alter table gd.mantenimiento_periferico enable row level security;

drop policy if exists mant_perif_tenant_isolation on gd.mantenimiento_periferico;
create policy mant_perif_tenant_isolation on gd.mantenimiento_periferico
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_mant_perif_updated_at
  before update on gd.mantenimiento_periferico
  for each row execute function app.touch_updated_at();

comment on table gd.mantenimiento_periferico is
  'GD-API-0138: mantenimiento preventivo/correctivo. tipo=auto_proteccion '
  'cuando el sistema lo crea automáticamente tras >5 fallos en 1h.';

-- ----------------------------------------------------------------------------
-- 23.4 — gd.agente_local_registro (GD-API-0139).
-- ----------------------------------------------------------------------------
create table if not exists gd.agente_local_registro (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  nombre_equipo text not null check (length(nombre_equipo) >= 2),
  version_agente text,
  -- Periféricos que controla este agente (puede manejar varios en un counter).
  periferico_ids uuid[] not null default '{}',
  fingerprint_publico bytea not null,
  -- Hash del token one-shot de emparejamiento (NUNCA el token claro).
  token_emparejamiento_hash text,
  token_emparejamiento_expira timestamptz,
  ultimo_handshake_en timestamptz,
  ultima_ip inet,
  estado text not null default 'pendiente' check (estado in (
    'pendiente', 'activo', 'revocado'
  )),
  motivo_revocacion text,
  registrado_por_user_id uuid not null references app.users(id) on delete restrict,
  fecha_registro timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ix_gd_agente_local_tenant_estado
  on gd.agente_local_registro(tenant_id, estado);
create index if not exists ix_gd_agente_local_fingerprint
  on gd.agente_local_registro(fingerprint_publico);

alter table gd.agente_local_registro enable row level security;

drop policy if exists agente_local_tenant_isolation on gd.agente_local_registro;
create policy agente_local_tenant_isolation on gd.agente_local_registro
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

create trigger trg_gd_agente_local_updated_at
  before update on gd.agente_local_registro
  for each row execute function app.touch_updated_at();

comment on table gd.agente_local_registro is
  'GD-API-0139: registro de agente local instalado en Counter. '
  'token_emparejamiento_hash es one-shot, expira 10 min. Tras éxito '
  'recibe JWT firmado del servidor (no almacenado aquí).';

-- ----------------------------------------------------------------------------
-- 23.5 — Seed permisos PERM-PER-001..012 (GD-API-0140).
-- ----------------------------------------------------------------------------
-- Columnas: codigo, nombre, modulo, descripcion, es_critico, estado.
insert into gd.permiso (codigo, modulo, nombre, descripcion, es_critico) values
  ('PERM-PER-001', 'perifericos', 'Administrar periféricos',
   'Crear/editar/configurar periféricos y puntos de atención.', true),
  ('PERM-PER-002', 'perifericos', 'Cambiar estado de periférico',
   'Activar/inactivar/mantenimiento/retirar periféricos.', true),
  ('PERM-PER-003', 'perifericos', 'Imprimir etiqueta de radicado',
   'Emitir comando de impresión de etiqueta para radicado.', false),
  ('PERM-PER-004', 'perifericos', 'Reimprimir etiqueta de radicado',
   'Reimpresión controlada con motivo (RFP-003).', true),
  ('PERM-PER-005', 'perifericos', 'Imprimir constancia de radicación',
   'Emitir comando de impresión de constancia formal.', false),
  ('PERM-PER-006', 'perifericos', 'Digitalizar documento individual',
   'Disparar digitalización individual desde escáner.', false),
  ('PERM-PER-007', 'perifericos', 'Digitalizar por lote',
   'Iniciar y finalizar lotes de digitalización.', false),
  ('PERM-PER-008', 'perifericos', 'Asociar digitalización a radicado cerrado',
   'Permite digitalizar/asociar archivos a radicados ya cerrados.', false),
  ('PERM-PER-009', 'perifericos', 'Reemplazar/corregir digitalización',
   'Sustituir digitalización por nueva versión con justificación.', true),
  ('PERM-PER-010', 'perifericos', 'Consultar uso propio de periféricos',
   'Ver historial de operaciones propias en periféricos.', false),
  ('PERM-PER-011', 'perifericos', 'Consultar uso global de periféricos',
   'Auditor/coordinador: ver historial de TODOS los usuarios.', false),
  ('PERM-PER-012', 'perifericos', 'Programar mantenimiento de periféricos',
   'Iniciar/finalizar mantenimiento de hardware.', true)
on conflict (codigo) do nothing;

-- Matriz rol↔permiso (idempotente):
--  Admin Sistema (ROL-001): todos los 12.
--  Coordinador VU (ROL-005): 002, 003, 004, 005, 006, 007, 008, 010, 011.
--  Radicador VU (ROL-004): 003, 005, 006, 007, 008, 010.
--  Auditor (ROL-016): 010, 011.
--  Admin Seguridad (ROL-002): 010, 011, 012.
do $$
declare
  v_admin_sis text := 'ROL-001';
  v_admin_seg text := 'ROL-002';
  v_radicador text := 'ROL-004';
  v_coord_vu  text := 'ROL-005';
  v_auditor   text := 'ROL-016';
  r record;
begin
  -- Admin sistema: todos.
  for r in select codigo from gd.permiso where modulo = 'perifericos' loop
    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default)
    values (v_admin_sis, r.codigo, 'institucional')
    on conflict do nothing;
  end loop;

  -- Coordinador VU.
  for r in select unnest(array[
    'PERM-PER-002','PERM-PER-003','PERM-PER-004','PERM-PER-005',
    'PERM-PER-006','PERM-PER-007','PERM-PER-008','PERM-PER-010','PERM-PER-011'
  ]) as cod loop
    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default)
    values (v_coord_vu, r.cod, 'dependencia')
    on conflict do nothing;
  end loop;

  -- Radicador VU.
  for r in select unnest(array[
    'PERM-PER-003','PERM-PER-005','PERM-PER-006','PERM-PER-007',
    'PERM-PER-008','PERM-PER-010'
  ]) as cod loop
    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default)
    values (v_radicador, r.cod, 'propio')
    on conflict do nothing;
  end loop;

  -- Auditor.
  for r in select unnest(array['PERM-PER-010','PERM-PER-011']) as cod loop
    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default)
    values (v_auditor, r.cod, 'institucional')
    on conflict do nothing;
  end loop;

  -- Admin Seguridad.
  for r in select unnest(array[
    'PERM-PER-010','PERM-PER-011','PERM-PER-012'
  ]) as cod loop
    insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default)
    values (v_admin_seg, r.cod, 'institucional')
    on conflict do nothing;
  end loop;
exception
  -- Si los roles no existen (entornos de test minimal), no fallar el schema.
  when foreign_key_violation then
    raise notice 'Roles no presentes; matriz rol↔perm periféricos pospuesta.';
end $$;

-- ----------------------------------------------------------------------------
-- 23.6 — Columnas adicionales en digitalizacion_documento para reemplazo
--        (GD-API-0142).
-- ----------------------------------------------------------------------------
-- Cuando se inserta una digitalización con reemplaza_a_id se debe (en service)
-- marcar la original con estado='reemplazada'. La original NO se borra
-- (DELETE bloqueado por trigger existente § 22.5).
alter table gd.digitalizacion_documento
  add column if not exists reemplaza_a_id uuid
    references gd.digitalizacion_documento(id) on delete restrict;
alter table gd.digitalizacion_documento
  add column if not exists motivo_reemplazo text;

create index if not exists ix_gd_digit_reemplaza
  on gd.digitalizacion_documento(reemplaza_a_id)
  where reemplaza_a_id is not null;

comment on column gd.digitalizacion_documento.reemplaza_a_id is
  'GD-API-0142: si esta fila reemplaza a otra (por calidad baja, etc.). '
  'La original queda con estado=reemplazada (DELETE bloqueado).';

-- =============================================================================
-- 24. GRANTs para el rol `copiloto_app`
-- =============================================================================
-- El rol `copiloto_app` es el usuario de la API (asyncpg pool). Sin estos
-- GRANTs cualquier query contra `gd.*` falla con `permission denied for
-- schema gd` ANTES de evaluar RLS — el chequeo de privilegios de schema
-- es previo al de policies. Mirror de los GRANTs de `app` y `influencer`
-- en `01-schema.sql` y `03-migrations.sql`.
--
-- RLS sigue siendo el gate primario por-fila (cada tabla con tenant_id
-- tiene su policy `tenant_id = app.current_tenant_id() or app.support_mode()`).
-- `copiloto_app` NO tiene BYPASSRLS, así que las policies aplican incluso
-- con estos GRANTs.
-- =============================================================================
grant usage on schema gd to copiloto_app;
grant select, insert, update, delete on all tables in schema gd to copiloto_app;
grant usage, select on all sequences in schema gd to copiloto_app;
grant execute on all functions in schema gd to copiloto_app;

-- Default privileges para tablas/sequences que se creen DESPUÉS de este
-- punto (ej. migraciones futuras que agreguen tablas a `gd`). Sin esto,
-- cada tabla nueva exigiría un GRANT explícito y se nos olvidaría.
alter default privileges in schema gd
  grant select, insert, update, delete on tables to copiloto_app;
alter default privileges in schema gd
  grant usage, select on sequences to copiloto_app;
alter default privileges in schema gd
  grant execute on functions to copiloto_app;

-- =============================================================================
-- Fin de bloque 21b. CIERRE EP-021. 142/142 tareas del backlog GD completadas.
-- =============================================================================

-- ============================================================================
-- Activación automática del módulo para Demo Taller (dev local)
-- ============================================================================
-- ON CONFLICT DO NOTHING: si el platform_owner ya hizo toggle manual desde la
-- UI, no sobreescribe. En prod este archivo NO debería cargarse — los
-- modules se activan via PATCH /v1/platform/tenant-modules/{tenant}/gestion_documental.
insert into app.tenant_modules (tenant_id, module, enabled, activated_at)
values ('11111111-1111-1111-1111-111111111111', 'gestion_documental', true, now())
on conflict (tenant_id, module) do nothing;
