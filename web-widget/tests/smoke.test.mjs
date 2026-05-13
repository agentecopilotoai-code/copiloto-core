// Smoke test: bootstraps the widget in jsdom against a fully mocked backend
// and asserts the FAB renders, the lead form posts, the chat form appears,
// and the polling loop is armed with the conversation id.
import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { createApi } from '../src/api.js';
import { createPoller } from '../src/poller.js';
import { createState } from '../src/state.js';
import { mountUi } from '../src/ui.js';

function bootDom() {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', {
    url: 'https://example.com/?utm_source=test',
    runScripts: 'outside-only',
  });
  global.window = dom.window;
  global.document = dom.window.document;
  global.URL = dom.window.URL;
  global.URLSearchParams = dom.window.URLSearchParams;
  global.FormData = dom.window.FormData;
  return dom;
}

test('mountUi paints the FAB and shows the lead form', async () => {
  bootDom();
  const config = {
    tenant: 'demo',
    widgetToken: 'tk',
    apiBase: 'https://api.example',
    assetBase: 'https://cdn.example/widget/v1',
    color: '#123456',
    greeting: 'hi',
    welcomeCopy: null,
    logoUrl: null,
    position: 'right',
    pollIntervalMs: 3000,
  };
  const state = createState();
  global.fetch = async () => ({
    ok: true,
    status: 201,
    statusText: 'Created',
    json: async () => ({}),
  });
  const api = createApi({ apiBase: config.apiBase, getSessionToken: () => state.sessionToken });
  const poller = createPoller({ api, intervalMs: config.pollIntervalMs, onNewMessage: () => {} });
  const ui = mountUi({ config, state, api, poller });
  assert.ok(ui.fab);
  assert.ok(ui.panel);
  assert.equal(document.querySelectorAll('.cpi-fab').length, 1);
  assert.equal(document.querySelector('form[data-form="lead"]').style.display, '');
  assert.equal(document.querySelector('form[data-form="chat"]').style.display, 'none');
  poller.stop();
});

test('lead form submit calls /v1/web/chat/start and arms the poller', async () => {
  bootDom();
  const config = {
    tenant: 'demo',
    widgetToken: 'tk',
    apiBase: 'https://api.example',
    assetBase: 'https://cdn.example/widget/v1',
    color: '#123456',
    greeting: 'hi',
    welcomeCopy: null,
    logoUrl: null,
    position: 'right',
    pollIntervalMs: 3000,
  };
  const state = createState();
  const fetchCalls = [];
  global.fetch = async (url, opts) => {
    fetchCalls.push({ url, opts });
    return {
      ok: true,
      status: 201,
      statusText: 'Created',
      json: async () => ({
        conversation_id: 'conv-1',
        contact_id: 'contact-1',
        session_token: 'sess-1',
        inbound_message_id: 'in-1',
        bot_reply: { id: 'out-1', body_text: 'hola desde el bot' },
      }),
    };
  };
  const api = createApi({ apiBase: config.apiBase, getSessionToken: () => state.sessionToken });
  const poller = createPoller({ api, intervalMs: 50, onNewMessage: () => {} });
  mountUi({ config, state, api, poller });

  const leadForm = document.querySelector('form[data-form="lead"]');
  leadForm.querySelector('input[name="name"]').value = 'Jane';
  leadForm.querySelector('textarea[name="message"]').value = 'Quiero info';
  leadForm.dispatchEvent(new window.Event('submit', { cancelable: true, bubbles: true }));
  await new Promise((r) => setTimeout(r, 30));

  assert.equal(fetchCalls.length, 1);
  assert.equal(fetchCalls[0].url, 'https://api.example/v1/web/chat/start');
  assert.equal(state.conversationId, 'conv-1');
  assert.equal(state.sessionToken, 'sess-1');
  assert.equal(poller.isRunning(), true);
  poller.stop();
});
