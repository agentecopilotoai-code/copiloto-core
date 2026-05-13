import test from 'node:test';
import assert from 'node:assert/strict';
import { createApi } from '../src/api.js';

function mockFetch(impl) {
  const calls = [];
  global.fetch = async (url, opts) => {
    calls.push({ url, opts });
    return impl(url, opts);
  };
  return calls;
}

test('createApi sends widget_token on start without Authorization', async () => {
  const calls = mockFetch(async () => ({
    ok: true,
    status: 201,
    statusText: 'Created',
    json: async () => ({ conversation_id: 'c1', session_token: 's1' }),
  }));
  const api = createApi({ apiBase: 'https://api.example', getSessionToken: () => null });
  const data = await api.start({ tenant_slug: 't', widget_token: 'w', name: 'A', message: 'hi' });
  assert.equal(data.conversation_id, 'c1');
  assert.equal(calls[0].url, 'https://api.example/v1/web/chat/start');
  assert.equal(calls[0].opts.method, 'POST');
  assert.equal(calls[0].opts.headers['Content-Type'], 'application/json');
  assert.equal(calls[0].opts.headers.Authorization, undefined);
});

test('createApi sends Bearer session token after start', async () => {
  const calls = mockFetch(async () => ({
    ok: true,
    status: 201,
    statusText: 'Created',
    json: async () => ({ inbound_message_id: 'm1' }),
  }));
  const api = createApi({ apiBase: 'https://api.example', getSessionToken: () => 'TOKEN' });
  await api.sendMessage('conv-1', 'hola');
  assert.equal(calls[0].url, 'https://api.example/v1/web/chat/conv-1/messages');
  assert.equal(calls[0].opts.headers.Authorization, 'Bearer TOKEN');
});

test('createApi.history GETs the right URL without body', async () => {
  const calls = mockFetch(async () => ({
    ok: true,
    status: 200,
    statusText: 'OK',
    json: async () => ({ conversation_id: 'c1', messages: [] }),
  }));
  const api = createApi({ apiBase: 'https://api.example', getSessionToken: () => 'TOKEN' });
  const data = await api.history('c1');
  assert.deepEqual(data.messages, []);
  assert.equal(calls[0].opts.method, 'GET');
  assert.equal(calls[0].opts.body, undefined);
});

test('createApi raises on non-ok response with detail', async () => {
  mockFetch(async () => ({
    ok: false,
    status: 401,
    statusText: 'Unauthorized',
    json: async () => ({ detail: 'Invalid widget token' }),
  }));
  const api = createApi({ apiBase: 'https://api.example', getSessionToken: () => null });
  await assert.rejects(() => api.start({}), /Invalid widget token/);
});
