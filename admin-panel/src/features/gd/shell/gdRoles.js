/**
 * gdRoles — etiquetas amigables de los roles del módulo GD.
 *
 * Source of truth: `app/gd/bootstrap.py::_GD_SYSTEM_ROLES`.
 *
 * Antes en la UI se veía "GD.ADMIN_SISTEMA" o "gd.admin_sistema" tal cual,
 * que es ilegible para usuarios no técnicos. Este helper traduce el código
 * canónico al nombre humano definido por producto + jerarquiza para que la
 * UI muestre el rol "más fuerte" cuando el usuario tiene varios.
 *
 * Si llega un código desconocido (rol custom creado por el tenant) se
 * formatea quitando el prefijo `gd.` y reemplazando `_` por espacios.
 */

const GD_ROLE_LABELS = {
  'gd.admin_sistema': 'Administrador del sistema',
  'gd.admin_seguridad': 'Administrador de seguridad',
  'gd.admin_documental': 'Administrador documental',
  'gd.radicador': 'Radicador (ventanilla)',
  'gd.coordinador_vu': 'Coordinador de ventanilla',
  'gd.admin_pqrsd': 'Administrador PQRSD',
  'gd.profesional': 'Profesional responsable',
  'gd.revisor': 'Revisor',
  'gd.jefe_dependencia': 'Jefe de dependencia',
  'gd.secretario_dependencia': 'Secretario de dependencia',
  'gd.usuario_dependencia': 'Usuario de dependencia',
  'gd.usuario_ci': 'Usuario de comunicación interna',
  'gd.usuario_radicacion_externa': 'Usuario radicación externa',
  'gd.firmante': 'Firmante autorizado',
  'gd.usuario_consulta': 'Usuario consulta',
  'gd.auditor': 'Auditor',
  'gd.admin_plantillas': 'Administrador de plantillas',
  'gd.agente_ia': 'Agente IA',
  'gd.robot_rpa': 'Robot RPA',
};

// Jerarquía decreciente — el primero que aparezca en `roles` se muestra
// como rol principal del usuario. Roles admin > operativos > consulta.
const GD_ROLE_RANK = [
  'gd.admin_sistema',
  'gd.admin_seguridad',
  'gd.admin_documental',
  'gd.admin_pqrsd',
  'gd.admin_plantillas',
  'gd.coordinador_vu',
  'gd.jefe_dependencia',
  'gd.firmante',
  'gd.revisor',
  'gd.profesional',
  'gd.radicador',
  'gd.secretario_dependencia',
  'gd.usuario_ci',
  'gd.usuario_radicacion_externa',
  'gd.usuario_dependencia',
  'gd.auditor',
  'gd.usuario_consulta',
  'gd.agente_ia',
  'gd.robot_rpa',
];

/**
 * Traduce un código (`gd.admin_sistema`) a su label humano.
 * Para roles custom desconocidos formatea legible: `gd.mi_rol_custom`
 * → `Mi rol custom`.
 */
export function gdRoleLabel(code) {
  if (!code) return 'Sin rol';
  if (GD_ROLE_LABELS[code]) return GD_ROLE_LABELS[code];
  const stripped = code.replace(/^gd\./, '').replace(/_/g, ' ');
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}

/**
 * Selecciona el rol "más fuerte" del array según `GD_ROLE_RANK`. Devuelve
 * el código canónico (o `null` si el array está vacío).
 *
 * Esto evita que la UI muestre `gd.usuario_consulta` cuando el usuario
 * además es `gd.admin_sistema`: prevalece el admin.
 */
export function gdRolePrimary(roles) {
  if (!Array.isArray(roles) || roles.length === 0) return null;
  for (const code of GD_ROLE_RANK) {
    if (roles.includes(code)) return code;
  }
  // Si ningún rol está en el ranking, devolvemos el primero (custom).
  return roles[0];
}

/**
 * Atajo: label legible del rol principal de un array de roles.
 */
export function gdPrimaryRoleLabel(roles) {
  const code = gdRolePrimary(roles);
  return gdRoleLabel(code);
}
