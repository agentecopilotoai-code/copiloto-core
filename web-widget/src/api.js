// Tiny wrapper around the public /v1/web/chat/* endpoints.
// Keeps fetch logic away from the DOM module so it can be unit tested in
// isolation under jsdom.

export function createApi({ apiBase, getSessionToken }) {
  function headers(body) {
    const h = {};
    if (body !== undefined) h['Content-Type'] = 'application/json';
    const token = getSessionToken();
    if (token) h['Authorization'] = 'Bearer ' + token;
    return h;
  }

  async function request(path, { method = 'GET', body } = {}) {
    const res = await fetch(apiBase + path, {
      method,
      headers: headers(body),
      body: body === undefined ? undefined : JSON.stringify(body),
      credentials: 'omit',
      mode: 'cors',
    });
    let data = null;
    try {
      data = await res.json();
    } catch (_e) {
      data = null;
    }
    if (!res.ok) {
      const err = new Error((data && data.detail) || res.statusText || 'request_failed');
      err.status = res.status;
      err.body = data;
      throw err;
    }
    return data;
  }

  return {
    start(payload) {
      return request('/v1/web/chat/start', { method: 'POST', body: payload });
    },
    sendMessage(conversationId, body) {
      return request('/v1/web/chat/' + conversationId + '/messages', {
        method: 'POST',
        body: { body },
      });
    },
    history(conversationId) {
      return request('/v1/web/chat/' + conversationId + '/messages');
    },
  };
}
