import { describe, expect, it } from 'vitest';

import {
  PERMISSIONS,
  ROLES,
  ROLE_HOME,
  can,
  highestRole,
  levelFor,
  resolveActiveRoles,
} from './matrix.js';

describe('PERMISSIONS matrix', () => {
  it('declara las 6 columnas para cada capability', () => {
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      for (const role of ROLES) {
        expect(row, `${key} sin columna ${role}`).toHaveProperty(role);
      }
    }
  });

  it('usa solo niveles válidos', () => {
    const VALID = new Set(['RW', 'R', 'partial', 'own_only', null]);
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      for (const role of ROLES) {
        expect(VALID.has(row[role]), `nivel inválido en ${key}.${role}=${row[role]}`).toBe(true);
      }
    }
  });

  it('capabilities platform.* son exclusivas de platform_owner', () => {
    for (const [key, row] of Object.entries(PERMISSIONS)) {
      if (!key.startsWith('platform.')) continue;
      expect(row.viewer, `${key} debería negar viewer`).toBeNull();
      expect(row.agent, `${key} debería negar agent`).toBeNull();
      expect(row.manager, `${key} debería negar manager`).toBeNull();
      expect(row.admin, `${key} debería negar admin`).toBeNull();
      expect(row.owner, `${key} debería negar owner`).toBeNull();
      expect(row.platform_owner, `${key} debería conceder platform_owner`).toBeTruthy();
    }
  });

  it('platform_owner NO ve capabilities de tenant', () => {
    const TENANT_ONLY = [
      'conversations.view', 'handoff.take', 'appointments.view',
      'services.write', 'campaigns.write', 'segments.write',
      'team.write', 'legal.write', 'audit.read',
    ];
    for (const cap of TENANT_ONLY) {
      expect(PERMISSIONS[cap].platform_owner, `${cap} no debe ser visible a platform_owner`).toBeNull();
    }
  });
});

describe('can()', () => {
  it('viewer puede leer conversaciones pero no tomarlas', () => {
    expect(can(['viewer'], 'conversations.view', 'R')).toBe(true);
    expect(can(['viewer'], 'conversations.view', 'RW')).toBe(false);
    expect(can(['viewer'], 'handoff.take', 'R')).toBe(false);
    expect(can(['viewer'], 'handoff.take', 'RW')).toBe(false);
  });

  it('agent puede tomar handoff y editar contactos parcialmente', () => {
    expect(can(['agent'], 'handoff.take', 'RW')).toBe(true);
    expect(can(['agent'], 'contacts.write', 'R')).toBe(true);
    expect(can(['agent'], 'contacts.write', 'RW')).toBe(false); // partial, no RW
  });

  it('manager gestiona segmentos y campañas pero no servicios', () => {
    expect(can(['manager'], 'segments.write', 'RW')).toBe(true);
    expect(can(['manager'], 'campaigns.write', 'RW')).toBe(true);
    expect(can(['manager'], 'services.write', 'RW')).toBe(false);
    expect(can(['manager'], 'services.write', 'R')).toBe(false);
  });

  it('admin gestiona servicios, paquetes, equipo y legal', () => {
    expect(can(['admin'], 'services.write', 'RW')).toBe(true);
    expect(can(['admin'], 'packages.write', 'RW')).toBe(true);
    expect(can(['admin'], 'team.write', 'RW')).toBe(true);
    expect(can(['admin'], 'legal.write', 'RW')).toBe(true);
    expect(can(['admin'], 'audit.read', 'R')).toBe(true);
  });

  it('owner tiene los mismos privilegios que admin sobre el tenant', () => {
    expect(can(['owner'], 'services.write', 'RW')).toBe(true);
    expect(can(['owner'], 'team.write', 'RW')).toBe(true);
    expect(can(['owner'], 'tenant_setup.write', 'RW')).toBe(true);
  });

  it('go_live_readiness.mark_live es exclusivo del owner del tenant', () => {
    // UI-016.1: marcar el tenant como live es una operación de cierre que solo
    // el owner del negocio debe poder ejecutar. Admin lee el checklist pero no
    // dispara el go-live.
    expect(can(['owner'], 'go_live_readiness.mark_live', 'RW')).toBe(true);
    expect(can(['owner'], 'go_live_readiness.read', 'R')).toBe(true);
    expect(can(['admin'], 'go_live_readiness.read', 'R')).toBe(true);
    expect(can(['admin'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
    expect(can(['manager'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
    expect(can(['platform_owner'], 'go_live_readiness.mark_live', 'RW')).toBe(false);
  });

  it('platform_owner accede a la flota pero NO al tenant', () => {
    expect(can(['platform_owner'], 'platform.tenants.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'platform.system_health.read', 'R')).toBe(true);
    expect(can(['platform_owner'], 'platform.feature_flags.write', 'RW')).toBe(true);
    expect(can(['platform_owner'], 'campaigns.write', 'R')).toBe(false);
    expect(can(['platform_owner'], 'conversations.view', 'R')).toBe(false);
  });

  it('roles vacíos o desconocidos → false (fail-closed)', () => {
    expect(can([], 'conversations.view', 'R')).toBe(false);
    expect(can(null, 'conversations.view', 'R')).toBe(false);
    expect(can(undefined, 'conversations.view', 'R')).toBe(false);
    expect(can(['unknown_role'], 'conversations.view', 'R')).toBe(false);
  });

  it('capability desconocida → false', () => {
    expect(can(['owner'], 'nonexistent.capability', 'R')).toBe(false);
  });

  it('multi-rol unifica al rol más permisivo', () => {
    // Un usuario que tiene viewer + manager → debe poder gestionar segmentos.
    expect(can(['viewer', 'manager'], 'segments.write', 'RW')).toBe(true);
    // viewer + agent → contactos.write partial ok en R, no RW.
    expect(can(['viewer', 'agent'], 'contacts.write', 'R')).toBe(true);
    expect(can(['viewer', 'agent'], 'contacts.write', 'RW')).toBe(false);
  });

  it('R por defecto cuando no se pasa mode', () => {
    expect(can(['agent'], 'contacts.write')).toBe(true);
    expect(can(['viewer'], 'segments.write')).toBe(false);
  });
});

describe('levelFor()', () => {
  it('retorna el nivel exacto declarado', () => {
    expect(levelFor(['viewer'], 'conversations.view')).toBe('R');
    expect(levelFor(['agent'], 'handoff.take')).toBe('RW');
    expect(levelFor(['agent'], 'contacts.write')).toBe('partial');
    expect(levelFor(['agent'], 'analytics.agent_performance.read')).toBe('own_only');
    expect(levelFor(['admin'], 'services.write')).toBe('RW');
  });

  it('elige el nivel más alto en multi-rol', () => {
    expect(levelFor(['viewer', 'admin'], 'services.write')).toBe('RW');
    expect(levelFor(['agent', 'manager'], 'contacts.write')).toBe('RW');
  });

  it('null cuando no hay acceso o capability inexistente', () => {
    expect(levelFor(['viewer'], 'campaigns.write')).toBeNull();
    expect(levelFor(['owner'], 'nope.nope')).toBeNull();
    expect(levelFor(null, 'conversations.view')).toBeNull();
  });
});

describe('highestRole()', () => {
  it('respeta jerarquía platform_owner > owner > admin > manager > agent > viewer', () => {
    expect(highestRole(['viewer', 'admin'])).toBe('admin');
    expect(highestRole(['agent', 'manager'])).toBe('manager');
    expect(highestRole(['owner'])).toBe('owner');
    expect(highestRole(['platform_owner', 'agent'])).toBe('platform_owner');
  });

  it('viewer como fallback seguro', () => {
    expect(highestRole([])).toBe('viewer');
    expect(highestRole(null)).toBe('viewer');
    expect(highestRole(undefined)).toBe('viewer');
    expect(highestRole(['unknown'])).toBe('viewer');
  });
});

describe('resolveActiveRoles()', () => {
  it('toma roles del tenant activo', () => {
    expect(resolveActiveRoles({ tenant: { roles: ['agent'] } })).toEqual(['agent']);
    expect(resolveActiveRoles({ tenant: { role: 'manager' } })).toEqual(['manager']);
  });

  it('platform_owner con support_mode hereda sus roles cross-tenant', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toContain('viewer');
    expect(roles).toContain('platform_owner');
  });

  it('owner con support_mode hereda sus roles', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toContain('owner');
  });

  it('support_mode SIN owner/platform_owner NO hereda', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['admin'], support_mode: true },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin support_mode los roles del profile no aplican', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
  });

  it('sin tenant ni roles globales → [] (fail-closed)', () => {
    expect(resolveActiveRoles({})).toEqual([]);
    // `admin` no es rol global; sin tenant activo no aplica.
    expect(resolveActiveRoles({ profile: { roles: ['admin'] } })).toEqual([]);
    expect(resolveActiveRoles({ profile: { roles: ['agent', 'manager'] } })).toEqual([]);
  });

  it('BUG-006: platform_owner SIN tenant aplica aunque support_mode sea false', () => {
    // Contexto: vistas globales de plataforma (`/platform`, IndexRedirect).
    // El platform_owner debe ser reconocido SIEMPRE — sin esto, el redirect
    // post-login lo manda al onboarding de tenant en vez de /platform.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['platform_owner']);
  });

  it('BUG-006: owner SIN tenant aplica aunque support_mode sea false', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['owner']);
  });

  it('BUG-006: sin tenant solo aplican roles globales — admin/agent del profile no se filtran', () => {
    // Si el profile trae [platform_owner, admin], solo platform_owner cuenta
    // a nivel global (admin no es rol global). El admin solo aplica dentro de
    // un tenant activo.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner', 'admin'], support_mode: false },
      tenant: null,
    });
    expect(roles).toEqual(['platform_owner']);
  });

  it('TASK-0077 preservado: platform_owner CON tenant requiere support_mode para heredar', () => {
    // El fix de BUG-006 NO debe romper TASK-0077: operar EN un tenant ajeno
    // con privilegios elevados sigue requiriendo support_mode explícito.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { roles: ['viewer'] },
    });
    expect(roles).toEqual(['viewer']);
    expect(roles).not.toContain('platform_owner');
  });

  it('deduplica', () => {
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { roles: ['owner', 'admin'] },
    });
    expect(roles.filter((r) => r === 'owner')).toHaveLength(1);
  });

  // ─── BUG-008: supportModeOverride opt-in temporal por tenant ──────────

  it('BUG-008: supportModeOverride matcheando tenant.id aplica roles globales', () => {
    // Replica el flujo "Ver como tenant": el frontend activó el toggle
    // via POST /v1/me/support-mode/{tenant.id}, así que aunque el JWT
    // tenga `support_mode=false`, el override del provider permite que
    // el rol global aplique en ESTE tenant.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-acme', roles: [] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toContain('platform_owner');
  });

  it('BUG-008: supportModeOverride scoped — NO aplica si tenant.id no matchea', () => {
    // El cookie es scoped a UN tenant_id. Si el user navega a OTRO
    // tenant donde NO activó el toggle, el override no debe filtrar
    // roles globales — sino reabriríamos el blast radius.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-other', roles: [] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toEqual([]);
    expect(roles).not.toContain('platform_owner');
  });

  it('BUG-008: supportModeOverride es noop sin rol global en profile', () => {
    // Sin rol global, el toggle no escala nada — solo permite que el
    // rol existente aplique cross-tenant. Para un user que NO es
    // platform_owner, el override es inocuo.
    const roles = resolveActiveRoles({
      profile: { roles: ['admin'], support_mode: false },
      tenant: { id: 'tenant-acme', roles: ['viewer'] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toEqual(['viewer']);
    expect(roles).not.toContain('admin');
  });

  it('BUG-008: support_mode del JWT (legacy) sigue funcionando sin override', () => {
    // El workaround viejo (BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE=true)
    // marca el user permanente. Ese path no se rompe con el fix.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { id: 'tenant-acme', roles: [] },
      supportModeOverride: null,
    });
    expect(roles).toContain('platform_owner');
  });

  it('BUG-008: comparison de tenant.id usa String() — UUID vs UUID-like string', () => {
    // El tenant.id puede llegar como UUID object o string (depende del
    // serializer). El override usa String() en ambos para no fallar por
    // comparación de tipos cuando son lógicamente iguales.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'abc-123', roles: [] },
      supportModeOverride: { tenantId: 'abc-123', expiresAt: null },
    });
    expect(roles).toContain('platform_owner');
  });

  // ─── BUG-012: support_mode inyecta `owner` para acceso tenant completo ──

  it('BUG-012: platform_owner en support_mode obtiene `owner` para capabilities tenant-scoped', () => {
    // Síntoma original (2026-05-17): platform_owner activa support_mode →
    // banner aparece OK → al entrar a /tenant-setup recibe "Acceso restringido"
    // porque la matriz tiene `platform_owner: null` para `tenant_setup.write`.
    // Sin `'owner'` inyectado, el feature pierde su propósito (acceso completo
    // al tenant target durante la sesión temporal).
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-acme', roles: [] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).toContain('platform_owner'); // mantiene su rol global
    expect(roles).toContain('owner');           // NUEVO: caps tenant heredadas
  });

  it('BUG-012: support_mode JWT legacy también inyecta `owner`', () => {
    // El workaround viejo (BOOTSTRAP_PLATFORM_OWNER_SUPPORT_MODE=true) que
    // marcaba el user con support_mode permanente también debe darle acceso
    // completo al tenant — sino, el fix solo aplicaría al toggle nuevo.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { id: 'tenant-acme', roles: [] },
      supportModeOverride: null,
    });
    expect(roles).toContain('owner');
  });

  it('BUG-012: SIN support_mode, platform_owner NO obtiene `owner` (no escala silenciosamente)', () => {
    // Defense en profundidad: el fix se gatea con `supportMode`. Sin el
    // toggle activo, el platform_owner sigue sin acceso al tenant — exactamente
    // como antes (TASK-0077 preservado).
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-acme', roles: ['viewer'] },
      supportModeOverride: null,
    });
    expect(roles).not.toContain('owner');
    expect(roles).not.toContain('platform_owner');
    expect(roles).toEqual(['viewer']);
  });

  it('BUG-012: support_mode con OTRO tenant (override no matchea) NO inyecta `owner`', () => {
    // El user activó support_mode contra tenant-acme pero está mirando
    // tenant-other. Sin matcheo, ni `platform_owner` ni `owner` deben
    // aparecer — sino, el cookie scoped pierde su valor.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: false },
      tenant: { id: 'tenant-other', roles: ['viewer'] },
      supportModeOverride: { tenantId: 'tenant-acme', expiresAt: null },
    });
    expect(roles).not.toContain('owner');
    expect(roles).not.toContain('platform_owner');
    expect(roles).toEqual(['viewer']);
  });

  it('BUG-012: `owner` global (sin platform_owner) en support_mode NO se inyecta owner adicional', () => {
    // Defensivo: la inyección de `'owner'` se gatea por
    // `profileGlobalRoles.includes('platform_owner')`. Un user con `owner`
    // global pero NO `platform_owner` no debería poder elevarse a `owner`
    // de OTRO tenant via support_mode (caso edge donde la cookie matchea
    // pero el user no es platform_owner real). El `'owner'` que ya tiene
    // en profileRoleList se suma vía el path normal, no por la inyección.
    const roles = resolveActiveRoles({
      profile: { roles: ['owner'], support_mode: true },
      tenant: { id: 'tenant-acme', roles: ['viewer'] },
    });
    // `owner` aparece porque viene de profileRoleList (support_mode lo
    // re-incluye), NO por la inyección de BUG-012.
    expect(roles).toContain('owner');
    expect(roles).toContain('viewer');
  });

  it('BUG-012: deduplica `owner` cuando ya viene del tenant', () => {
    // Si el tenant del platform_owner es uno donde ya es `owner` real
    // (caso raro: platform_owner que también tiene rol owner asignado en
    // ese tenant), no debe aparecer duplicado en el array final.
    const roles = resolveActiveRoles({
      profile: { roles: ['platform_owner'], support_mode: true },
      tenant: { id: 'tenant-acme', roles: ['owner'] },
    });
    expect(roles.filter((r) => r === 'owner')).toHaveLength(1);
  });
});

describe('ROLE_HOME', () => {
  it('declara landing para todos los roles', () => {
    for (const role of ROLES) {
      expect(ROLE_HOME[role], `landing faltante para ${role}`).toBeTruthy();
    }
  });

  it('agent aterriza en operations-desk, platform_owner en fleet', () => {
    expect(ROLE_HOME.agent).toBe('operations-desk');
    expect(ROLE_HOME.platform_owner).toBe('platform-fleet');
  });

  it('viewer aterriza en viewer-summary (UI-010.1)', () => {
    expect(ROLE_HOME.viewer).toBe('viewer-summary');
  });
});

describe('UI-INFLU-002 — Módulo Influencer capabilities', () => {
  const INFLU_CAPS = [
    'influencer.module.access',
    'influencer.personas.read',
    'influencer.personas.write',
    'influencer.personas.archive',
    'influencer.generate',
    'influencer.channels.connect',
    'influencer.posts.schedule',
    'influencer.posts.approve_publish',
    'influencer.credits.read',
    'influencer.credits.topup',
    'influencer.ai_providers.configure',
  ];

  it('declara las 11 capabilities del módulo', () => {
    for (const cap of INFLU_CAPS) {
      expect(PERMISSIONS[cap], `${cap} no declarada`).toBeDefined();
    }
  });

  it('viewer y agent NO tienen acceso al módulo (capability `module.access` null)', () => {
    expect(PERMISSIONS['influencer.module.access'].viewer).toBeNull();
    expect(PERMISSIONS['influencer.module.access'].agent).toBeNull();
  });

  it('manager tiene acceso de lectura pero NO compra créditos ni conecta plataformas', () => {
    expect(PERMISSIONS['influencer.module.access'].manager).toBe('R');
    expect(PERMISSIONS['influencer.personas.write'].manager).toBe('RW');
    expect(PERMISSIONS['influencer.generate'].manager).toBe('RW');
    expect(PERMISSIONS['influencer.credits.topup'].manager).toBeNull();
    expect(PERMISSIONS['influencer.channels.connect'].manager).toBeNull();
    expect(PERMISSIONS['influencer.personas.archive'].manager).toBeNull();
  });

  it('admin/owner pueden archivar, conectar canales y comprar créditos', () => {
    for (const role of ['admin', 'owner']) {
      expect(PERMISSIONS['influencer.personas.archive'][role]).toBe('RW');
      expect(PERMISSIONS['influencer.channels.connect'][role]).toBe('RW');
      expect(PERMISSIONS['influencer.credits.topup'][role]).toBe('RW');
    }
  });

  it('platform_owner es el ÚNICO que configura proveedores IA (D3 del backlog)', () => {
    const row = PERMISSIONS['influencer.ai_providers.configure'];
    expect(row.platform_owner).toBe('RW');
    for (const role of ['viewer', 'agent', 'manager', 'admin', 'owner']) {
      expect(row[role], `${role} no debe configurar providers`).toBeNull();
    }
  });

  it('platform_owner NO tiene acceso operativo al módulo (config-only, no operación)', () => {
    expect(PERMISSIONS['influencer.module.access'].platform_owner).toBeNull();
    expect(PERMISSIONS['influencer.personas.write'].platform_owner).toBeNull();
    expect(PERMISSIONS['influencer.generate'].platform_owner).toBeNull();
    expect(PERMISSIONS['influencer.credits.topup'].platform_owner).toBeNull();
  });
});
