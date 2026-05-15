/**
 * Resuelve la config de navegación (`nav.js`) a items renderizables.
 *
 * Para cada `module id` de cada sección busca su metadata en `modules` y evalúa
 * la `capability` con `permissions.can(...)`. Comporta:
 *   - id sin módulo registrado → se omite (vistas aún no implementadas).
 *   - sin permiso y `includeDenied=false` → se omite.
 *   - sin permiso y `includeDenied=true` → se incluye con `disabled: true`
 *     (el shell read-only lo pinta en la sección "Sin acceso").
 *   - secciones que quedan sin items visibles → se descartan.
 *
 * @param {Array<{section: string, items: string[]}>} navGroups
 * @param {Array<object>} modules  - `adminModules` de `app/modules.js`.
 * @param {{ can: (cap: string, mode?: 'R'|'RW') => boolean }} permissions
 * @param {{ includeDenied?: boolean }} [options]
 * @returns {Array<{section: string, items: Array<{id, label, capability, disabled}>}>}
 */
export function resolveNav(navGroups, modules, permissions, { includeDenied = false } = {}) {
  const byId = new Map(modules.map((module) => [module.id, module]));
  const resolved = [];

  for (const group of navGroups) {
    const items = [];
    for (const id of group.items) {
      const module = byId.get(id);
      if (!module) continue;
      const allowed = !module.capability || permissions.can(module.capability, 'R');
      if (!allowed && !includeDenied) continue;
      items.push({
        id: module.id,
        label: module.label,
        capability: module.capability ?? null,
        disabled: !allowed,
      });
    }
    if (items.length > 0) {
      resolved.push({ section: group.section, items });
    }
  }

  return resolved;
}
