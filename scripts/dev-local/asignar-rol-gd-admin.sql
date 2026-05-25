-- ============================================================================
-- LOCAL DEV — Asignar rol gd.admin_sistema al usuario actual en Demo Taller
-- ============================================================================
-- USO:
--   docker compose exec postgres psql -U copiloto_admin -d copilotoia \
--     -v target_email='tu-email@dominio.com' \
--     -f /scripts/asignar-rol-gd-admin.sql
--
-- (o copy-paste el contenido al psql interactivo, reemplazando :target_email
--  por tu correo entre comillas simples)
--
-- ¿Qué hace?
--   1. Asegura que los 19 roles del sistema GD existen en gd.rol
--   2. Encuentra tu user_id (por email) en Demo Taller
--   3. Crea tu gd.perfil_usuario en estado 'activo'
--   4. Asigna el rol 'gd.admin_sistema' con alcance 'global'
--
-- ¿Por qué `gd.admin_sistema`?
--   Es el rol MÁS ALTO en GD (ROL-001 de la Matriz de Roles). Tiene
--   acceso transversal: configura usuarios, roles, dependencias, parámetros
--   institucionales, periféricos, integraciones, salud del sistema, etc.
--   Es el equivalente GD del "owner" del producto principal.
--
--   Otros roles operativos (ROL-007 profesional, ROL-009 jefe_dependencia,
--   ROL-014 firmante, etc.) son más limitados. Si querés probar flujos
--   específicos (ej. firmar documentos como ROL-014), podés agregar
--   asignaciones adicionales con otros rol_codigo.
--
-- IDEMPOTENTE: usa ON CONFLICT DO NOTHING — se puede correr múltiples
-- veces sin duplicar filas.
-- ============================================================================

\set ON_ERROR_STOP on

\echo ''
\echo '── 1/4 Seed de los 19 roles GD del sistema ──────────────────'

insert into gd.rol (codigo, nombre, descripcion, es_sistema, estado)
values
  ('gd.admin_sistema',          'Administrador del Sistema',          'Configura usuarios, roles, dependencias, parámetros institucionales', true, 'activo'),
  ('gd.admin_seguridad',        'Administrador de Seguridad',         'Gestiona política de contraseñas, sesiones, auditoría de seguridad', true, 'activo'),
  ('gd.admin_documental',       'Administrador Documental',           'Gestiona TRD/TVD, series, subseries, tipos documentales, expedientes', true, 'activo'),
  ('gd.radicador',              'Radicador Ventanilla Única',         'Crea radicados de entrada/salida, opera periféricos', true, 'activo'),
  ('gd.coordinador_vu',         'Coordinador Ventanilla Única',       'Supervisa cola VU, anulaciones, reasignaciones', true, 'activo'),
  ('gd.admin_pqrsd',            'Administrador PQRSD',                'Asigna PQRSD, monitorea términos, supervisa proceso', true, 'activo'),
  ('gd.profesional',            'Profesional Responsable',            'Gestiona PQRSD y correspondencia asignadas, proyecta respuestas', true, 'activo'),
  ('gd.revisor',                'Revisor',                            'Revisa documentos antes de aprobación', true, 'activo'),
  ('gd.jefe_dependencia',       'Jefe de Dependencia',                'Aprueba documentos, reasigna dentro de su dependencia', true, 'activo'),
  ('gd.secretario_dependencia', 'Secretario de Dependencia',          'RW limitado en buzón de dependencia, correspondencia', true, 'activo'),
  ('gd.usuario_dependencia',    'Usuario de Dependencia',             'Acceso básico a su buzón y tareas asignadas', true, 'activo'),
  ('gd.usuario_ci',             'Usuario Comunicación Interna',       'Crea, envía, recibe correspondencia interna', true, 'activo'),
  ('gd.usuario_radicacion_externa','Usuario Radicación Externa',      'Crea correspondencia externa desde dependencia', true, 'activo'),
  ('gd.firmante',               'Firmante Autorizado',                'Firma electrónicamente documentos aprobados', true, 'activo'),
  ('gd.usuario_consulta',       'Usuario Consulta',                   'Acceso solo-lectura a radicados/documentos/trazabilidad', true, 'activo'),
  ('gd.auditor',                'Auditor',                            'Consulta eventos de auditoría + reportes auditables', true, 'activo'),
  ('gd.admin_plantillas',       'Administrador de Plantillas',        'CRUD de plantillas institucionales + versionamiento', true, 'activo'),
  ('gd.agente_ia',              'Agente IA (identidad técnica)',      'Identidad para llamadas IA — sin UI', true, 'activo'),
  ('gd.robot_rpa',              'Robot RPA (identidad técnica)',      'Identidad para integraciones RPA — sin UI', true, 'activo')
on conflict (codigo) do nothing;

\echo '  → 19 roles asegurados (gd.rol).'

\echo ''
\echo '── 2/4 Identificar tu user_id en Demo Taller ────────────────'

-- Busca el user_id del email que pongas con `-v target_email='...'`.
-- Si no pasaste -v, usa el primer owner del tenant Demo Taller
-- (en local con Auth0 + first-login el primer usuario que entra suele
-- ser el owner del tenant).
\if :{?target_email}
  \echo '  Buscando user por email:' :target_email
\else
  \set target_email 'NULL'
  \echo '  Sin -v target_email: usaré el PRIMER user con role=owner en Demo Taller.'
\endif

-- Resolvemos el user_id y lo guardamos en una psql var para usarlo después.
select u.id::text as resolved_user_id, u.email, u.display_name
from app.users u
where u.id in (
  select tm.user_id
  from app.tenant_members tm
  where tm.tenant_id = '11111111-1111-1111-1111-111111111111'
    and (:'target_email' = 'NULL' or u.email = :'target_email')
  order by case when tm.role = 'owner' then 0 else 1 end, tm.created_at
  limit 1
)
\gset

\if :{?resolved_user_id}
  \echo '  ✓ user_id resuelto:' :resolved_user_id
  \echo '    email:' :email
  \echo '    display_name:' :display_name
\else
  \echo '  ✗ NO encontré ningún user en Demo Taller. ¿Hiciste primer login con Auth0?'
  \echo '    Si no, abre http://localhost:3000/admin/ y loguea primero.'
  \quit
\endif

\echo ''
\echo '── 3/4 Crear gd.perfil_usuario (estado=activo) ──────────────'

-- En support_mode el platform_owner ve filas de cualquier tenant.
-- Acá necesitamos saltarnos RLS para INSERT. Usamos el rol superuser
-- del container (que somos: copiloto_admin). Si la policy bloquea, el
-- INSERT falla con detalle claro.
set app.support_mode = 'true';

insert into gd.perfil_usuario (
  tenant_id, user_id,
  tipo_vinculacion, estado_gd,
  fecha_inicio_vinculacion
)
values (
  '11111111-1111-1111-1111-111111111111',
  :'resolved_user_id'::uuid,
  'planta', 'activo',
  current_date
)
on conflict (tenant_id, user_id) do update
  set estado_gd = 'activo',
      updated_at = now();

\echo '  ✓ perfil_usuario creado / actualizado a estado=activo.'

\echo ''
\echo '── 4/4 Asignar rol gd.admin_sistema con alcance global ──────'

insert into gd.asignacion_alcance (
  tenant_id, user_id, rol_codigo,
  alcance, fecha_inicio, estado, motivo
)
values (
  '11111111-1111-1111-1111-111111111111',
  :'resolved_user_id'::uuid,
  'gd.admin_sistema',
  'global', current_date, 'activa',
  'Bootstrap dev-local: rol admin para Demo Taller'
)
on conflict do nothing;

\echo '  ✓ Rol gd.admin_sistema asignado (alcance global).'

\echo ''
\echo '── Verificación ──────────────────────────────────────────────'

select
  p.estado_gd                  as perfil_estado,
  p.tipo_vinculacion,
  array_agg(a.rol_codigo)      as roles_asignados,
  array_agg(a.alcance)         as alcances
from gd.perfil_usuario p
left join gd.asignacion_alcance a
  on a.tenant_id = p.tenant_id
  and a.user_id = p.user_id
  and a.estado = 'activa'
where p.tenant_id = '11111111-1111-1111-1111-111111111111'
  and p.user_id = :'resolved_user_id'::uuid
group by p.estado_gd, p.tipo_vinculacion;

\echo ''
\echo '✅ Listo. Refrescá el navegador (Cmd+Shift+R) e ingresá a Gestión Documental.'
\echo '   Verás el sidebar completo con todas las secciones (admin_sistema tiene acceso a todo).'
