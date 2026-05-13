// Polls GET /v1/web/chat/{conversation_id}/messages every `intervalMs` to pick
// up bot or human-operator replies that arrived after the initial response.
// Dedupes by message id so we never append the same bubble twice.

export function createPoller({ api, intervalMs, onNewMessage, onError }) {
  let timer = null;
  let conversationId = null;
  let seen = new Set();
  let inflight = false;

  async function tick() {
    if (!conversationId || inflight) return;
    inflight = true;
    try {
      const data = await api.history(conversationId);
      const msgs = (data && data.messages) || [];
      for (const m of msgs) {
        if (m.id && !seen.has(m.id)) {
          seen.add(m.id);
          if (typeof onNewMessage === 'function') onNewMessage(m);
        }
      }
    } catch (err) {
      if (typeof onError === 'function') onError(err);
    } finally {
      inflight = false;
    }
  }

  return {
    start(conversation, opts = {}) {
      conversationId = conversation;
      if (Array.isArray(opts.knownIds)) {
        seen = new Set(opts.knownIds);
      }
      this.stop();
      timer = setInterval(tick, intervalMs);
    },
    stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    },
    markSeen(id) {
      if (id) seen.add(id);
    },
    isRunning() {
      return timer !== null;
    },
    _tick: tick,
  };
}
