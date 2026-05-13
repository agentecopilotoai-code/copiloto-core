// Reads configuration from the embedding <script> tag's data-* attributes.
// All customisation (colours, logo, copy, button position) flows through this
// module so the IIFE bundle can be re-used across tenants without rebuilds.

export const POLL_INTERVAL_MS = 3000;
export const DEFAULT_COLOR = '#1f7ae0';
export const DEFAULT_GREETING = 'Hola 👋, ¿en qué te podemos ayudar?';
export const DEFAULT_POSITION = 'right';

function pickScript() {
  if (typeof document === 'undefined') return null;
  if (document.currentScript) return document.currentScript;
  return document.querySelector('script[data-widget-token][data-tenant]');
}

function readQueryParam(name) {
  if (typeof window === 'undefined' || !window.location) return null;
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
  } catch (_e) {
    return null;
  }
}

export function readConfig(scriptEl) {
  const el = scriptEl || pickScript();
  if (!el) return null;
  const tenant = el.getAttribute('data-tenant');
  const widgetToken = el.getAttribute('data-widget-token');
  if (!tenant || !widgetToken) return null;
  let apiBase = '';
  try {
    apiBase = new URL(el.src || '', window.location.href).origin;
  } catch (_e) {
    apiBase = window.location.origin;
  }
  return {
    tenant,
    widgetToken,
    apiBase,
    color: el.getAttribute('data-color') || DEFAULT_COLOR,
    greeting: el.getAttribute('data-greeting') || DEFAULT_GREETING,
    logoUrl: el.getAttribute('data-logo') || null,
    welcomeCopy: el.getAttribute('data-welcome') || null,
    position: (el.getAttribute('data-position') || DEFAULT_POSITION).toLowerCase() === 'left' ? 'left' : 'right',
    referrerContactId: (el.getAttribute('data-ref') || readQueryParam('ref') || '').trim() || null,
    pollIntervalMs: POLL_INTERVAL_MS,
  };
}

export function readUtm() {
  if (typeof window === 'undefined') return {};
  try {
    const params = new URLSearchParams(window.location.search);
    return {
      utm_source: params.get('utm_source') || undefined,
      utm_medium: params.get('utm_medium') || undefined,
      utm_campaign: params.get('utm_campaign') || undefined,
      referrer: document.referrer || undefined,
    };
  } catch (_e) {
    return {};
  }
}
