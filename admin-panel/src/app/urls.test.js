import { describe, it, expect } from 'vitest';

import {
  platformAdminUrl,
  gdHome, gdAdmin,
  influencerHome, influencerAdmin,
  chatbotHome, chatbotAdmin,
  parseModuleUrl, legacyRedirectFor,
  isKnownModule, ROUTE_PATTERNS,
} from './urls.js';

describe('urls — builders por módulo', () => {
  describe('platformAdminUrl', () => {
    it('home', () => {
      expect(platformAdminUrl()).toBe('/admin');
    });
    it('sub-path', () => {
      expect(platformAdminUrl('/tenants')).toBe('/admin/tenants');
      expect(platformAdminUrl('tenants/new')).toBe('/admin/tenants/new');
    });
  });

  describe('gdHome', () => {
    it('home del módulo', () => {
      expect(gdHome('demo')).toBe('/gd/t/demo');
    });
    it('sub-path operacional', () => {
      expect(gdHome('demo', '/buzon')).toBe('/gd/t/demo/buzon');
      expect(gdHome('demo', 'pqrsd/mias')).toBe('/gd/t/demo/pqrsd/mias');
    });
    it('redirige sub-path /admin/* al admin del módulo', () => {
      // Defensa: si un componente compone `/admin/usuarios` y lo pasa a
      // gdHome por error, NO genera `/gd/t/demo/admin/usuarios` (URL
      // ambigua). Se promueve a `/gd/admin/t/demo/usuarios`.
      expect(gdHome('demo', '/admin/usuarios')).toBe('/gd/admin/t/demo/usuarios');
    });
    it('lanza error sin slug', () => {
      expect(() => gdHome()).toThrow(/slug/);
      expect(() => gdHome(null)).toThrow(/slug/);
    });
  });

  describe('gdAdmin', () => {
    it('home admin', () => {
      expect(gdAdmin('demo')).toBe('/gd/admin/t/demo');
    });
    it('sub-path', () => {
      expect(gdAdmin('demo', '/usuarios')).toBe('/gd/admin/t/demo/usuarios');
      expect(gdAdmin('demo', '/estructura')).toBe('/gd/admin/t/demo/estructura');
    });
  });

  describe('influencerHome / influencerAdmin', () => {
    it('builders', () => {
      expect(influencerHome('demo')).toBe('/influencer/t/demo');
      expect(influencerHome('demo', '/casting')).toBe('/influencer/t/demo/casting');
      expect(influencerAdmin('demo')).toBe('/influencer/admin/t/demo');
      expect(influencerAdmin('demo', '/usuarios')).toBe('/influencer/admin/t/demo/usuarios');
    });
  });

  describe('chatbotHome / chatbotAdmin', () => {
    it('builders', () => {
      expect(chatbotHome('demo')).toBe('/chatbot/t/demo');
      expect(chatbotHome('demo', '/contacts/123')).toBe('/chatbot/t/demo/contacts/123');
      expect(chatbotAdmin('demo')).toBe('/chatbot/admin/t/demo');
    });
  });
});

describe('urls — parseModuleUrl', () => {
  it('operación GD', () => {
    expect(parseModuleUrl('/gd/t/demo')).toEqual({
      module: 'gd', mode: 'op', slug: 'demo', subPath: '/',
    });
    expect(parseModuleUrl('/gd/t/demo/buzon')).toEqual({
      module: 'gd', mode: 'op', slug: 'demo', subPath: '/buzon',
    });
    expect(parseModuleUrl('/gd/t/demo/pqrsd/abc-123')).toEqual({
      module: 'gd', mode: 'op', slug: 'demo', subPath: '/pqrsd/abc-123',
    });
  });
  it('admin GD', () => {
    expect(parseModuleUrl('/gd/admin/t/demo')).toEqual({
      module: 'gd', mode: 'admin', slug: 'demo', subPath: '/',
    });
    expect(parseModuleUrl('/gd/admin/t/demo/usuarios')).toEqual({
      module: 'gd', mode: 'admin', slug: 'demo', subPath: '/usuarios',
    });
  });
  it('influencer + chatbot', () => {
    expect(parseModuleUrl('/influencer/t/demo/casting').module).toBe('influencer');
    expect(parseModuleUrl('/influencer/admin/t/demo').mode).toBe('admin');
    expect(parseModuleUrl('/chatbot/t/demo').module).toBe('chatbot');
  });
  it('no-tenant / platform admin / inválido', () => {
    expect(parseModuleUrl('/admin/tenants')).toBeNull();
    expect(parseModuleUrl('/')).toBeNull();
    expect(parseModuleUrl('')).toBeNull();
    expect(parseModuleUrl(null)).toBeNull();
    expect(parseModuleUrl('/gd')).toBeNull();           // sin /t/
    expect(parseModuleUrl('/foo/t/demo')).toBeNull();   // módulo desconocido
  });
});

describe('urls — legacyRedirectFor', () => {
  it('migra /t/{slug}/gd → /gd/t/{slug}', () => {
    expect(legacyRedirectFor('/t/demo/gd')).toBe('/gd/t/demo');
    expect(legacyRedirectFor('/t/demo/gd/buzon')).toBe('/gd/t/demo/buzon');
    expect(legacyRedirectFor('/t/demo/gd/pqrsd/mias')).toBe('/gd/t/demo/pqrsd/mias');
  });
  it('migra /t/{slug}/gd/admin/* → /gd/admin/t/{slug}/*', () => {
    expect(legacyRedirectFor('/t/demo/gd/admin/usuarios'))
      .toBe('/gd/admin/t/demo/usuarios');
    expect(legacyRedirectFor('/t/demo/gd/admin/estructura'))
      .toBe('/gd/admin/t/demo/estructura');
  });
  it('migra /t/{slug}/influencer/* → /influencer/t/{slug}/*', () => {
    expect(legacyRedirectFor('/t/demo/influencer'))
      .toBe('/influencer/t/demo');
    expect(legacyRedirectFor('/t/demo/influencer/personas/abc/studio'))
      .toBe('/influencer/t/demo/personas/abc/studio');
  });
  it('migra resto (chatbot) → /chatbot/t/{slug}/*', () => {
    expect(legacyRedirectFor('/t/demo/contacts/abc'))
      .toBe('/chatbot/t/demo/contacts/abc');
    expect(legacyRedirectFor('/t/demo/agente'))
      .toBe('/chatbot/t/demo/agente');
  });
  it('NO migra /t/{slug}/read/* (read-only shell aparte)', () => {
    expect(legacyRedirectFor('/t/demo/read/dashboard')).toBeNull();
  });
  it('NO migra /t/{slug} sola (TenantHomeRedirect en otro sitio)', () => {
    expect(legacyRedirectFor('/t/demo')).toBeNull();
  });
  it('null para URLs no legacy', () => {
    expect(legacyRedirectFor('/gd/t/demo/buzon')).toBeNull();
    expect(legacyRedirectFor('/admin/tenants')).toBeNull();
    expect(legacyRedirectFor('/')).toBeNull();
    expect(legacyRedirectFor('')).toBeNull();
    expect(legacyRedirectFor(null)).toBeNull();
  });
});

describe('urls — misc', () => {
  it('isKnownModule', () => {
    expect(isKnownModule('gd')).toBe(true);
    expect(isKnownModule('influencer')).toBe(true);
    expect(isKnownModule('chatbot')).toBe(true);
    expect(isKnownModule('foo')).toBe(false);
    expect(isKnownModule('')).toBe(false);
  });
  it('ROUTE_PATTERNS expone los literales', () => {
    expect(ROUTE_PATTERNS.GD_OP).toBe('/gd/t/:tenantSlug/*');
    expect(ROUTE_PATTERNS.GD_ADMIN).toBe('/gd/admin/t/:tenantSlug/*');
    expect(ROUTE_PATTERNS.LEGACY_TENANT).toBe('/t/:tenantSlug/*');
  });
});
