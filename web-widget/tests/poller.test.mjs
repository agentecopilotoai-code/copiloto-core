import test from 'node:test';
import assert from 'node:assert/strict';
import { createPoller } from '../src/poller.js';

function makeApi(batches) {
  let i = 0;
  return {
    async history(_conversationId) {
      const batch = batches[Math.min(i, batches.length - 1)];
      i += 1;
      return { messages: batch };
    },
  };
}

test('poller dedupes messages by id across ticks', async () => {
  const seen = [];
  const api = makeApi([
    [{ id: 'a', body_text: 'hi', direction: 'inbound' }],
    [
      { id: 'a', body_text: 'hi', direction: 'inbound' },
      { id: 'b', body_text: 'bot', direction: 'outbound' },
    ],
  ]);
  const poller = createPoller({
    api,
    intervalMs: 1000,
    onNewMessage: (m) => seen.push(m.id),
  });
  poller.start('conv-1');
  await poller._tick();
  await poller._tick();
  poller.stop();
  assert.deepEqual(seen, ['a', 'b']);
});

test('poller respects knownIds so the initial reply is not duplicated', async () => {
  const seen = [];
  const api = makeApi([
    [
      { id: 'inbound-1', direction: 'inbound', body_text: 'hi' },
      { id: 'reply-1', direction: 'outbound', body_text: 'bot' },
      { id: 'new-1', direction: 'outbound', body_text: 'follow-up' },
    ],
  ]);
  const poller = createPoller({
    api,
    intervalMs: 1000,
    onNewMessage: (m) => seen.push(m.id),
  });
  poller.start('conv-1', { knownIds: ['inbound-1', 'reply-1'] });
  await poller._tick();
  poller.stop();
  assert.deepEqual(seen, ['new-1']);
});

test('poller stops cleanly and is not running afterwards', () => {
  const poller = createPoller({
    api: { history: async () => ({ messages: [] }) },
    intervalMs: 3000,
    onNewMessage: () => {},
  });
  poller.start('conv-1');
  assert.equal(poller.isRunning(), true);
  poller.stop();
  assert.equal(poller.isRunning(), false);
});

test('poller invokes onError without throwing when history fails', async () => {
  const errors = [];
  const poller = createPoller({
    api: {
      history: async () => {
        throw new Error('boom');
      },
    },
    intervalMs: 1000,
    onNewMessage: () => {},
    onError: (e) => errors.push(e.message),
  });
  poller.start('conv-1');
  await poller._tick();
  poller.stop();
  assert.deepEqual(errors, ['boom']);
});
