/**
 * Matriz de permisos UI — Módulo Gestión Documental.
 *
 * Espejo defensivo del backend `gd.rol_permiso` (~152 permisos × 19 roles).
 * Fuente: `docs/gestion documental/MATRIZ_PERMISOS.md`.
 *
 * El backend hace el enforce real con JWT + RLS multi-tenant; esta matriz
 * decide qué se muestra/oculta en el frontend (sidebar, botones, rutas).
 * Si el backend rechaza, mostramos `<AccessDenied />`.
 *
 * Convenciones:
 *   - Permisos codificados como `MOD-COD` (ej. 'VU-001', 'PQRSD-018').
 *     Sin prefijo `PERM-` para reducir verbosidad.
 *   - Valores:
 *       - 'RW' → puede ejecutar la acción y leer su resultado.
 *       - 'R'  → solo lectura del recurso o reporte.
 *       - null → sin acceso (oculta menús/CTAs).
 *   - Alcance se evalúa server-side; aquí solo nivel binario UI.
 */

export const GD_ROLES = Object.freeze([
  'gd.admin_sistema',          // ROL-001
  'gd.admin_seguridad',        // ROL-002
  'gd.admin_documental',       // ROL-003
  'gd.radicador',              // ROL-004
  'gd.coordinador_vu',         // ROL-005
  'gd.admin_pqrsd',            // ROL-006
  'gd.profesional',            // ROL-007
  'gd.revisor',                // ROL-008
  'gd.jefe_dependencia',       // ROL-009
  'gd.secretario_dependencia', // ROL-010
  'gd.usuario_dependencia',    // ROL-011
  'gd.usuario_ci',             // ROL-012
  'gd.usuario_radicacion_externa', // ROL-013
  'gd.firmante',               // ROL-014
  'gd.usuario_consulta',       // ROL-015
  'gd.auditor',                // ROL-016
  'gd.admin_plantillas',       // ROL-017
  // ROL-018/019 son identidades técnicas — sin UI.
]);

const RW = 'RW';
const R = 'R';

// Roles de ayuda para reducir verbosidad.
const OPERATIVOS = [
  'gd.profesional', 'gd.revisor', 'gd.jefe_dependencia',
  'gd.secretario_dependencia', 'gd.usuario_dependencia',
];
const VU = ['gd.radicador', 'gd.coordinador_vu'];

/**
 * Helper: construye fila con role → access. Roles no listados → null.
 */
function row(map) {
  const result = {};
  for (const r of GD_ROLES) {
    result[r] = map[r] ?? null;
  }
  return Object.freeze(result);
}

function all(level) {
  const m = {};
  for (const r of GD_ROLES) m[r] = level;
  return m;
}

function any(roles, level) {
  const m = {};
  for (const r of roles) m[r] = level;
  return m;
}

export const GD_PERMISSIONS = Object.freeze({
  // ────────────────── identidad / usuarios ─────────────────────────────
  'USR-001': row({ 'gd.admin_sistema': RW }),
  'USR-002': row({ 'gd.admin_sistema': RW }),
  'USR-004': row({ 'gd.admin_sistema': RW }),
  'USR-005': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': RW }),
  'USR-006': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': RW }),
  'USR-007': row({ 'gd.admin_sistema': RW }),
  'USR-008': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': RW }),
  'USR-009': row({ 'gd.admin_sistema': RW, 'gd.jefe_dependencia': RW }),
  'USR-010': row({
    'gd.admin_sistema': R, 'gd.admin_seguridad': R, 'gd.auditor': R,
    'gd.jefe_dependencia': R, 'gd.coordinador_vu': R,
  }),
  'USR-011': row({ 'gd.admin_sistema': RW }),
  'USR-012': row({ 'gd.admin_sistema': RW }),

  // ────────────────── roles_catalogo ───────────────────────────────────
  'ROL-001': row(all(R)),  // todos consultan
  'ROL-002': row({ 'gd.admin_sistema': RW }),
  'ROL-003': row({ 'gd.admin_sistema': RW }),
  'ROL-004': row({ 'gd.admin_sistema': RW }),
  'ROL-005': row({ 'gd.admin_sistema': RW }),
  'ROL-006': row({ 'gd.admin_sistema': RW }),

  // ────────────────── ventanilla (PERM-VU-*) ───────────────────────────
  'VU-001': row(any(VU, RW)),     // crear entrada
  'VU-002': row(any(VU, RW)),     // crear salida
  'VU-005': row(any(VU, RW)),     // clasificar inicialmente
  'VU-006': row({ 'gd.coordinador_vu': RW }),  // reclasificar
  'VU-014': row({ 'gd.coordinador_vu': RW }),  // corregir datos menores
  'VU-015': row(any(VU, RW)),                   // solicitar anulación
  'VU-016': row({ 'gd.coordinador_vu': RW }),   // aprobar anulación
  'VU-021': row({ 'gd.coordinador_vu': RW, 'gd.admin_sistema': RW }), // contingencia

  // ────────────────── PQRSD ────────────────────────────────────────────
  'PQRSD-006': row({ 'gd.admin_pqrsd': RW }),
  'PQRSD-007': row({ 'gd.admin_pqrsd': RW, 'gd.jefe_dependencia': RW }),
  'PQRSD-008': row({ 'gd.admin_pqrsd': RW, 'gd.jefe_dependencia': RW }),
  'PQRSD-009': row({ 'gd.profesional': RW }),
  'PQRSD-012': row({ 'gd.profesional': RW }),
  'PQRSD-013': row({ 'gd.revisor': RW, 'gd.jefe_dependencia': RW }),
  'PQRSD-015': row({ 'gd.jefe_dependencia': RW }),
  'PQRSD-016': row({ 'gd.jefe_dependencia': RW }),
  'PQRSD-017': row(any(VU, RW)),
  'PQRSD-018': row({ 'gd.admin_pqrsd': RW, 'gd.jefe_dependencia': RW }),
  'PQRSD-019': row({ 'gd.admin_pqrsd': RW, 'gd.jefe_dependencia': RW }),
  'PQRSD-020': row({ 'gd.admin_pqrsd': RW, 'gd.jefe_dependencia': RW }),
  // lectura: cualquier operativo + auditor.
  'PQRSD-READ': row({
    ...any(OPERATIVOS, R),
    'gd.admin_pqrsd': R, 'gd.coordinador_vu': R,
    'gd.auditor': R, 'gd.usuario_consulta': R,
  }),

  // ────────────────── correspondencia interna ──────────────────────────
  'CI-001': row({ 'gd.usuario_ci': RW, 'gd.profesional': RW,
                  'gd.secretario_dependencia': RW }),
  'CI-002': row({ ...any(OPERATIVOS, R), 'gd.usuario_ci': R,
                   'gd.auditor': R }),
  'CI-005': row({ 'gd.usuario_ci': RW, 'gd.jefe_dependencia': RW }),

  // ────────────────── correspondencia externa ──────────────────────────
  'CE-001': row({ 'gd.usuario_radicacion_externa': RW,
                   'gd.secretario_dependencia': RW }),
  'CE-005': row({ 'gd.revisor': RW, 'gd.jefe_dependencia': RW }),
  'CE-006': row({ 'gd.jefe_dependencia': RW }),
  'CE-009': row({ 'gd.coordinador_vu': RW }),  // anular

  // ────────────────── documentos ────────────────────────────────────────
  'DOC-001': row({ ...any(OPERATIVOS, RW), 'gd.usuario_ci': RW,
                    'gd.usuario_radicacion_externa': RW }),
  'DOC-002': row({ ...any(OPERATIVOS, R), 'gd.usuario_consulta': R,
                    'gd.auditor': R, 'gd.admin_documental': R }),
  'DOC-005': row({ 'gd.profesional': RW, 'gd.usuario_ci': RW,
                    'gd.usuario_radicacion_externa': RW }),
  'DOC-006': row({ 'gd.coordinador_vu': RW, 'gd.admin_documental': RW }),

  // ────────────────── firmas ───────────────────────────────────────────
  'FIR-001': row({ 'gd.firmante': RW, 'gd.jefe_dependencia': RW }),
  'FIR-002': row({ 'gd.firmante': RW, 'gd.jefe_dependencia': RW }),
  'FIR-005': row({ 'gd.firmante': RW, 'gd.admin_sistema': RW }),
  'FIR-READ': row({
    ...any(OPERATIVOS, R), 'gd.firmante': R, 'gd.auditor': R,
  }),

  // ────────────────── plantillas ───────────────────────────────────────
  'PLA-001': row({ 'gd.admin_plantillas': RW, 'gd.admin_sistema': RW }),
  'PLA-002': row({ 'gd.admin_plantillas': RW }),
  'PLA-003': row({ 'gd.admin_plantillas': RW }),
  'PLA-USE': row({
    ...any(OPERATIVOS, R), ...any(VU, R),
    'gd.usuario_ci': R, 'gd.usuario_radicacion_externa': R,
  }),

  // ────────────────── TRD/TVD ──────────────────────────────────────────
  'TRD-001': row({ 'gd.admin_documental': RW }),
  'TRD-002': row({ 'gd.admin_documental': RW }),
  'TRD-003': row({ 'gd.admin_documental': RW }),  // editor jerárquico
  'TRD-READ': row({
    ...any(OPERATIVOS, R), ...any(VU, R), 'gd.auditor': R,
    'gd.admin_documental': R, 'gd.admin_sistema': R,
  }),
  'EXP-001': row({ 'gd.admin_documental': RW, 'gd.profesional': RW }),
  'EXP-READ': row({
    ...any(OPERATIVOS, R), 'gd.auditor': R, 'gd.admin_documental': R,
    'gd.usuario_consulta': R,
  }),

  // ────────────────── correo importado ─────────────────────────────────
  'COR-001': row(any(VU, RW)),
  'COR-002': row(any(VU, RW)),  // descartar correo
  'COR-READ': row({ ...any(VU, R), 'gd.auditor': R }),

  // ────────────────── reportes ─────────────────────────────────────────
  'REP-001': row({ 'gd.coordinador_vu': R, 'gd.admin_pqrsd': R,
                    'gd.jefe_dependencia': R, 'gd.auditor': R,
                    'gd.admin_sistema': R }),
  'REP-004': row({ 'gd.coordinador_vu': RW, 'gd.admin_pqrsd': RW,
                    'gd.auditor': RW, 'gd.admin_sistema': RW }),  // exportar
  'REP-008': row({ 'gd.auditor': RW, 'gd.admin_sistema': RW,
                    'gd.coordinador_vu': RW }),
  'REP-009': row({ 'gd.jefe_dependencia': R, 'gd.auditor': R }),

  // ────────────────── auditoría ────────────────────────────────────────
  'AUD-001': row({ 'gd.auditor': R, 'gd.admin_seguridad': R,
                    'gd.admin_sistema': R }),
  'AUD-005': row({ 'gd.auditor': RW }),

  // ────────────────── periféricos (Doc 6) ──────────────────────────────
  'PER-001': row({ 'gd.admin_sistema': RW }),  // admin periféricos
  'PER-002': row({ 'gd.admin_sistema': RW }),  // estado periféricos
  'PER-003': row(any(VU, RW)),                  // imprimir etiqueta
  'PER-004': row({ 'gd.coordinador_vu': RW }),  // reimprimir
  'PER-005': row(any(VU, RW)),                  // imprimir constancia
  'PER-006': row(any(VU, RW)),                  // digitalizar individual
  'PER-007': row(any(VU, RW)),                  // digitalizar lote
  'PER-008': row({ 'gd.coordinador_vu': RW }),  // asociar a cerrado
  'PER-009': row({ 'gd.coordinador_vu': RW, 'gd.admin_sistema': RW }),  // reemplazar digit
  'PER-010': row({ ...any(VU, R), 'gd.auditor': R }),  // uso propio
  'PER-011': row({ 'gd.coordinador_vu': R, 'gd.auditor': R,
                    'gd.admin_sistema': R }),  // uso global
  'PER-012': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': RW }),

  // ────────────────── notificaciones ───────────────────────────────────
  'NOT-READ': row(all(R)),
  'NOT-PREF': row(all(RW)),

  // ────────────────── seguridad ────────────────────────────────────────
  'SEG-PWD': row({ 'gd.admin_seguridad': RW }),
  'SEG-SES': row({ 'gd.admin_seguridad': RW, 'gd.admin_sistema': R }),
  'SEG-MFA': row({ 'gd.admin_seguridad': RW, 'gd.admin_sistema': R }),

  // ────────────────── admin sistema (EP-008) ───────────────────────────
  'EST-001': row({ 'gd.admin_sistema': RW }),    // estructura orgánica
  'EST-READ': row({ ...any(OPERATIVOS, R), 'gd.admin_sistema': R,
                    'gd.auditor': R, 'gd.coordinador_vu': R }),
  'CAT-001': row({ 'gd.admin_sistema': RW }),    // catálogos institucionales
  'PAR-001': row({ 'gd.admin_sistema': RW }),    // parámetros sistema
  'CAL-001': row({ 'gd.admin_sistema': RW }),    // calendario laboral
  'NOT-TPL': row({ 'gd.admin_sistema': RW }),    // plantillas notificación
  'LOG-001': row({ 'gd.admin_sistema': RW, 'gd.auditor': R }),  // retención logs
  'BAK-001': row({ 'gd.admin_sistema': R }),     // backup (solo consulta)
  'INT-001': row({ 'gd.admin_sistema': RW }),    // integraciones externas
  'SAL-001': row({ 'gd.admin_sistema': R, 'gd.admin_seguridad': R,
                    'gd.auditor': R }),           // salud del sistema

  // ────────────────── IA embebida (EP-010) ─────────────────────────────
  // GD-UI-0072: sugerencia clasificación — operativos + VU usan (al
  // radicar/clasificar); admin documental lee resultados.
  'IA-001': row({ ...any(OPERATIVOS, RW), ...any(VU, RW),
                   'gd.admin_pqrsd': RW, 'gd.admin_documental': RW }),
  // GD-UI-0073: resumir documento/expediente.
  'IA-002': row({ ...any(OPERATIVOS, RW), 'gd.admin_pqrsd': RW,
                   'gd.admin_documental': RW, 'gd.usuario_consulta': R,
                   'gd.auditor': R }),
  // GD-UI-0074: búsqueda semántica — todo consultor + operativos.
  'IA-003': row({ ...any(OPERATIVOS, RW), ...any(VU, RW),
                   'gd.admin_pqrsd': RW, 'gd.usuario_consulta': RW,
                   'gd.admin_documental': RW, 'gd.auditor': R }),
  // GD-UI-0075: asistente conversacional rol-aware.
  'IA-004': row({ ...any(OPERATIVOS, RW), 'gd.coordinador_vu': RW,
                   'gd.admin_pqrsd': RW, 'gd.admin_sistema': RW,
                   'gd.admin_documental': RW }),
  // GD-UI-0076: detección PII — operativos (al cargar adjunto) +
  // admin seguridad (revisión global).
  'IA-005': row({ ...any(OPERATIVOS, RW), ...any(VU, RW),
                   'gd.admin_pqrsd': RW, 'gd.admin_seguridad': RW,
                   'gd.admin_sistema': R }),
  // GD-UI-0077: panel uso + costos — admin sistema (global), jefe (su
  // dependencia), usuario (solo el propio).
  'IA-006': row({ 'gd.admin_sistema': RW, 'gd.jefe_dependencia': R,
                   'gd.coordinador_vu': R, 'gd.admin_pqrsd': R,
                   'gd.auditor': R }),
  // GD-UI-0077: límites por usuario — solo admin sistema escribe.
  'IA-007': row({ 'gd.admin_sistema': RW, 'gd.jefe_dependencia': R }),
  // GD-UI-0078: config modelos IA — solo admin sistema.
  'IA-008': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': R }),

  // ────────────────── Correo institucional (EP-011 / UI-13) ────────────
  // GD-UI-0079 buzón correo entrante — VU + operativos + admin PQRSD.
  'COR-EMAIL-001': row({ ...any(VU, RW), ...any(OPERATIVOS, R),
                          'gd.admin_pqrsd': RW, 'gd.admin_sistema': R }),
  // GD-UI-0079 convertir correo → radicado — solo VU / coord.
  'COR-EMAIL-002': row({ ...any(VU, RW), 'gd.admin_pqrsd': RW }),
  // GD-UI-0080 composer saliente — operativos + VU.
  'COR-EMAIL-003': row({ ...any(OPERATIVOS, RW), ...any(VU, RW),
                          'gd.admin_pqrsd': RW, 'gd.usuario_ci': RW,
                          'gd.usuario_radicacion_externa': RW }),
  // GD-UI-0084 config canales SMTP/IMAP — solo admin sistema.
  'COR-EMAIL-004': row({ 'gd.admin_sistema': RW, 'gd.admin_seguridad': R }),
  // GD-UI-0085 reglas auto-clasif — admin sistema + coordinador VU.
  'COR-EMAIL-005': row({ 'gd.admin_sistema': RW,
                          'gd.coordinador_vu': RW, 'gd.admin_pqrsd': RW }),
  // GD-UI-0086 dashboard salud canal correo.
  'COR-EMAIL-006': row({ 'gd.admin_sistema': R, 'gd.admin_seguridad': R,
                          'gd.coordinador_vu': R, 'gd.auditor': R }),

  // ────────────────── Alertas críticas (EP-012 / UI-13) ────────────────
  // GD-UI-0083 ver alertas críticas — jefes, admin, auditor (R).
  'ALR-001': row({ 'gd.admin_sistema': R, 'gd.admin_seguridad': R,
                    'gd.jefe_dependencia': R, 'gd.coordinador_vu': R,
                    'gd.admin_pqrsd': R, 'gd.auditor': R }),
  // GD-UI-0083 atender alerta — los responsables del ámbito.
  'ALR-002': row({ 'gd.admin_sistema': RW, 'gd.jefe_dependencia': RW,
                    'gd.coordinador_vu': RW, 'gd.admin_pqrsd': RW }),
});

/**
 * `gdCan(roleCode, permissionCode, mode)` — true si el rol GD tiene
 * el permiso UI con el modo solicitado o superior (RW > R).
 *
 * Si el usuario tiene múltiples roles GD (lo permite el backend en
 * `gd.asignacion_alcance`), `gdCanAny(roleCodes, ...)` aplica el OR.
 */
export function gdCan(roleCode, permissionCode, mode = 'R') {
  if (!roleCode || !permissionCode) return false;
  const row = GD_PERMISSIONS[permissionCode];
  if (!row) return false;
  const access = row[roleCode];
  if (access === null || access === undefined) return false;
  if (mode === 'R') return access === 'R' || access === 'RW';
  return access === 'RW';
}

export function gdCanAny(roleCodes, permissionCode, mode = 'R') {
  if (!Array.isArray(roleCodes) || roleCodes.length === 0) return false;
  return roleCodes.some((r) => gdCan(r, permissionCode, mode));
}

/**
 * `gdLandingFor(roleCode)` — devuelve la ruta de landing del rol GD.
 * Mapa de UI_BACKLOG.md sección 3.
 */
export const GD_LANDING_BY_ROLE = Object.freeze({
  'gd.admin_sistema': '/gd/admin/usuarios',
  'gd.admin_seguridad': '/gd/seguridad',
  'gd.admin_documental': '/gd/trd',
  'gd.radicador': '/gd/ventanilla',
  'gd.coordinador_vu': '/gd/ventanilla/cola',
  'gd.admin_pqrsd': '/gd/pqrsd',
  'gd.profesional': '/gd/buzon',
  'gd.revisor': '/gd/buzon',
  'gd.jefe_dependencia': '/gd/buzon/dependencia',
  'gd.secretario_dependencia': '/gd/buzon/dependencia',
  'gd.usuario_dependencia': '/gd/buzon',
  'gd.usuario_ci': '/gd/correspondencia/interna',
  'gd.usuario_radicacion_externa': '/gd/correspondencia/externa',
  'gd.firmante': '/gd/firmas/por-firmar',
  'gd.usuario_consulta': '/gd/consulta',
  'gd.auditor': '/gd/auditoria',
  'gd.admin_plantillas': '/gd/plantillas',
});

export function gdLandingFor(roleCodes) {
  if (Array.isArray(roleCodes)) {
    for (const r of roleCodes) {
      const target = GD_LANDING_BY_ROLE[r];
      if (target) return target;
    }
  } else if (typeof roleCodes === 'string') {
    return GD_LANDING_BY_ROLE[roleCodes] ?? '/gd';
  }
  return '/gd';
}

/**
 * Determina si el usuario tiene AL MENOS un permiso GD activo.
 * Se usa para mostrar/ocultar el item top-level "Gestión Documental".
 */
export function hasAnyGdAccess(roleCodes) {
  if (!Array.isArray(roleCodes) || roleCodes.length === 0) return false;
  return roleCodes.some((r) => GD_ROLES.includes(r));
}
