import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { readConfig, POLL_INTERVAL_MS, DEFAULT_COLOR, DEFAULT_GREETING } from '../src/config.js';

function setup(scriptAttrs, { search = '' } = {}) {
  const dom = new JSDOM(`<!doctype html><html><body></body></html>`, {
    url: 'https://cdn.copilotoia.com/widget/v1/widget.js' + search,
  });
  global.window = dom.window;
  global.document = dom.window.document;
  global.URL = dom.window.URL;
  global.URLSearchParams = dom.window.URLSearchParams;
  const script = dom.window.document.createElement('script');
  for (const [k, v] of Object.entries(scriptAttrs)) script.setAttribute(k, v);
  script.src = 'https://cdn.copilotoia.com/widget/v1/widget.js';
  return { dom, script };
}

test('readConfig returns null when token is missing', () => {
  const { script } = setup({ 'data-tenant': 'demo' });
  assert.equal(readConfig(script), null);
});

test('readConfig captures all data-* attributes with defaults', () => {
  const { script } = setup({
    'data-tenant': 'demo',
    'data-widget-token': 'abc',
  });
  const cfg = readConfig(script);
  assert.equal(cfg.tenant, 'demo');
  assert.equal(cfg.widgetToken, 'abc');
  assert.equal(cfg.color, DEFAULT_COLOR);
  assert.equal(cfg.greeting, DEFAULT_GREETING);
  assert.equal(cfg.position, 'right');
  assert.equal(cfg.pollIntervalMs, POLL_INTERVAL_MS);
  assert.equal(cfg.apiBase, 'https://cdn.copilotoia.com');
});

test('readConfig honours custom color, logo, position and welcome copy', () => {
  const { script } = setup({
    'data-tenant': 'demo',
    'data-widget-token': 'abc',
    'data-color': '#ff0000',
    'data-greeting': 'Hola!',
    'data-logo': 'https://cdn/example/logo.png',
    'data-welcome': 'Atendemos 24/7',
    'data-position': 'LEFT',
  });
  const cfg = readConfig(script);
  assert.equal(cfg.color, '#ff0000');
  assert.equal(cfg.greeting, 'Hola!');
  assert.equal(cfg.logoUrl, 'https://cdn/example/logo.png');
  assert.equal(cfg.welcomeCopy, 'Atendemos 24/7');
  assert.equal(cfg.position, 'left');
});

test('readConfig reads referrer contact id from query string', () => {
  const { script } = setup(
    { 'data-tenant': 'demo', 'data-widget-token': 'abc' },
    { search: '?ref=11111111-1111-1111-1111-111111111111' }
  );
  const cfg = readConfig(script);
  assert.equal(cfg.referrerContactId, '11111111-1111-1111-1111-111111111111');
});
