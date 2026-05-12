/*
 * CopilotoIA Web Widget (TASK-0039)
 *
 * Embed on any site with:
 *   <script async src="https://<host>/admin/widget.js"
 *           data-tenant="<tenant_slug>"
 *           data-widget-token="<widget_token>"
 *           data-color="#1f7ae0"
 *           data-greeting="¿En qué te ayudamos?"></script>
 *
 * The widget renders a floating chat bubble in the lower-right corner.
 * It collects a lead-capture form (name + optional phone/email + message)
 * before the first turn, then chats with the bot synchronously via the
 * /v1/web/chat endpoints. UTM parameters and document.referrer are sent
 * with the start call so the contact is tagged with lead_source.
 */
(function () {
  'use strict';
  if (window.__copilotoiaWidgetLoaded) return;
  window.__copilotoiaWidgetLoaded = true;

  var scriptEl =
    document.currentScript ||
    document.querySelector('script[data-widget-token][data-tenant]');
  if (!scriptEl) return;

  var tenant = scriptEl.getAttribute('data-tenant');
  var widgetToken = scriptEl.getAttribute('data-widget-token');
  var color = scriptEl.getAttribute('data-color') || '#1f7ae0';
  var greeting =
    scriptEl.getAttribute('data-greeting') ||
    'Hola 👋, ¿en qué te podemos ayudar?';
  if (!tenant || !widgetToken) {
    console.warn('[copilotoia] Missing data-tenant or data-widget-token');
    return;
  }

  var apiBase = '';
  try {
    var src = new URL(scriptEl.src, window.location.href);
    apiBase = src.origin;
  } catch (e) {
    apiBase = window.location.origin;
  }

  function readUtm() {
    var params = new URLSearchParams(window.location.search);
    return {
      utm_source: params.get('utm_source') || undefined,
      utm_medium: params.get('utm_medium') || undefined,
      utm_campaign: params.get('utm_campaign') || undefined,
      referrer: document.referrer || undefined,
    };
  }

  function injectStyles() {
    var css =
      '.cpi-fab{position:fixed;right:20px;bottom:20px;z-index:2147483600;background:' +
      color +
      ';color:#fff;border:none;border-radius:9999px;width:60px;height:60px;font-size:28px;cursor:pointer;box-shadow:0 6px 24px rgba(0,0,0,.2);}\n' +
      '.cpi-panel{position:fixed;right:20px;bottom:90px;z-index:2147483600;width:340px;max-width:calc(100vw - 40px);height:480px;max-height:calc(100vh - 110px);background:#fff;border-radius:14px;box-shadow:0 18px 50px rgba(0,0,0,.25);display:flex;flex-direction:column;overflow:hidden;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#111;}\n' +
      '.cpi-header{background:' +
      color +
      ';color:#fff;padding:12px 14px;display:flex;align-items:center;justify-content:space-between;}\n' +
      '.cpi-header h3{margin:0;font-size:15px;font-weight:600;}\n' +
      '.cpi-close{background:transparent;border:none;color:#fff;font-size:22px;cursor:pointer;line-height:1;}\n' +
      '.cpi-body{flex:1;overflow-y:auto;padding:12px;background:#f7f8fa;}\n' +
      '.cpi-msg{display:block;margin:6px 0;padding:8px 12px;border-radius:12px;max-width:85%;line-height:1.4;font-size:14px;white-space:pre-wrap;word-wrap:break-word;}\n' +
      '.cpi-msg.bot,.cpi-msg.system{background:#fff;border:1px solid #e5e7eb;color:#111;}\n' +
      '.cpi-msg.user{background:' +
      color +
      ';color:#fff;margin-left:auto;text-align:left;}\n' +
      '.cpi-form{padding:12px;background:#fff;border-top:1px solid #e5e7eb;display:flex;flex-direction:column;gap:8px;}\n' +
      '.cpi-form input,.cpi-form textarea{font:inherit;font-size:13px;padding:8px 10px;border:1px solid #d1d5db;border-radius:8px;outline:none;}\n' +
      '.cpi-form textarea{resize:none;min-height:54px;}\n' +
      '.cpi-form button{background:' +
      color +
      ';color:#fff;border:none;border-radius:8px;padding:10px;font-size:14px;font-weight:600;cursor:pointer;}\n' +
      '.cpi-form button[disabled]{opacity:.6;cursor:not-allowed;}\n' +
      '.cpi-footer{padding:6px 10px;font-size:11px;color:#6b7280;text-align:center;background:#fff;border-top:1px solid #f1f5f9;}\n' +
      '.cpi-row{display:flex;gap:6px;align-items:flex-end;}\n' +
      '.cpi-row textarea{flex:1;}\n' +
      '.cpi-row button{flex:0 0 auto;}';
    var style = document.createElement('style');
    style.setAttribute('data-copilotoia-widget', '1');
    style.appendChild(document.createTextNode(css));
    document.head.appendChild(style);
  }

  var state = {
    open: false,
    sessionToken: null,
    conversationId: null,
    started: false,
    sending: false,
  };

  var elements = {};

  function build() {
    var fab = document.createElement('button');
    fab.className = 'cpi-fab';
    fab.setAttribute('aria-label', 'Abrir chat');
    fab.textContent = '💬';
    fab.addEventListener('click', toggle);
    document.body.appendChild(fab);
    elements.fab = fab;

    var panel = document.createElement('div');
    panel.className = 'cpi-panel';
    panel.style.display = 'none';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', 'CopilotoIA chat');
    panel.innerHTML =
      '<header class="cpi-header"><h3>Asistente</h3>' +
      '<button type="button" class="cpi-close" aria-label="Cerrar">×</button>' +
      '</header>' +
      '<div class="cpi-body" id="cpi-body"></div>' +
      '<form class="cpi-form" id="cpi-form-lead">' +
      '<input type="text" name="name" placeholder="Nombre *" required maxlength="160"/>' +
      '<input type="tel" name="phone" placeholder="Teléfono (opcional)" maxlength="32"/>' +
      '<input type="email" name="email" placeholder="Email (opcional)" maxlength="320"/>' +
      '<textarea name="message" placeholder="¿En qué te ayudamos? *" required maxlength="4000"></textarea>' +
      '<button type="submit">Enviar</button>' +
      '</form>' +
      '<form class="cpi-form" id="cpi-form-chat" style="display:none;">' +
      '<div class="cpi-row"><textarea name="body" placeholder="Escribe tu mensaje..." required maxlength="4000"></textarea>' +
      '<button type="submit">➤</button></div>' +
      '</form>' +
      '<div class="cpi-footer">Powered by CopilotoIA</div>';
    document.body.appendChild(panel);
    elements.panel = panel;
    elements.body = panel.querySelector('#cpi-body');
    elements.leadForm = panel.querySelector('#cpi-form-lead');
    elements.chatForm = panel.querySelector('#cpi-form-chat');
    panel.querySelector('.cpi-close').addEventListener('click', toggle);
    elements.leadForm.addEventListener('submit', onLeadSubmit);
    elements.chatForm.addEventListener('submit', onChatSubmit);

    appendMessage('system', greeting);
  }

  function toggle() {
    state.open = !state.open;
    elements.panel.style.display = state.open ? 'flex' : 'none';
  }

  function appendMessage(role, text) {
    var msg = document.createElement('div');
    msg.className = 'cpi-msg ' + role;
    msg.textContent = text;
    elements.body.appendChild(msg);
    elements.body.scrollTop = elements.body.scrollHeight;
  }

  function setSending(form, sending) {
    var btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = sending;
  }

  function jsonRequest(path, options) {
    options = options || {};
    var headers = options.headers || {};
    headers['Content-Type'] = 'application/json';
    if (state.sessionToken) {
      headers['Authorization'] = 'Bearer ' + state.sessionToken;
    }
    return fetch(apiBase + path, {
      method: options.method || 'GET',
      headers: headers,
      body: options.body ? JSON.stringify(options.body) : undefined,
      credentials: 'omit',
      mode: 'cors',
    }).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) {
          var err = new Error((data && data.detail) || res.statusText || 'request_failed');
          err.status = res.status;
          throw err;
        }
        return data;
      });
    });
  }

  function onLeadSubmit(event) {
    event.preventDefault();
    if (state.sending) return;
    var formData = new FormData(elements.leadForm);
    var utm = readUtm();
    var body = {
      tenant_slug: tenant,
      widget_token: widgetToken,
      name: (formData.get('name') || '').toString().trim(),
      phone: (formData.get('phone') || '').toString().trim() || undefined,
      email: (formData.get('email') || '').toString().trim() || undefined,
      message: (formData.get('message') || '').toString().trim(),
      utm_source: utm.utm_source,
      utm_medium: utm.utm_medium,
      utm_campaign: utm.utm_campaign,
      referrer: utm.referrer,
    };
    if (!body.name || !body.message) return;
    state.sending = true;
    setSending(elements.leadForm, true);
    appendMessage('user', body.message);
    jsonRequest('/v1/web/chat/start', { method: 'POST', body: body })
      .then(function (data) {
        state.sessionToken = data.session_token;
        state.conversationId = data.conversation_id;
        state.started = true;
        if (data.bot_reply && data.bot_reply.body_text) {
          appendMessage('bot', data.bot_reply.body_text);
        }
        elements.leadForm.style.display = 'none';
        elements.chatForm.style.display = 'flex';
        elements.chatForm.querySelector('textarea').focus();
      })
      .catch(function (err) {
        appendMessage('system', 'No pudimos iniciar el chat: ' + (err.message || 'error'));
      })
      .finally(function () {
        state.sending = false;
        setSending(elements.leadForm, false);
      });
  }

  function onChatSubmit(event) {
    event.preventDefault();
    if (state.sending || !state.conversationId) return;
    var textarea = elements.chatForm.querySelector('textarea');
    var body = (textarea.value || '').trim();
    if (!body) return;
    textarea.value = '';
    appendMessage('user', body);
    state.sending = true;
    setSending(elements.chatForm, true);
    jsonRequest('/v1/web/chat/' + state.conversationId + '/messages', {
      method: 'POST',
      body: { body: body },
    })
      .then(function (data) {
        if (data.bot_reply && data.bot_reply.body_text) {
          appendMessage('bot', data.bot_reply.body_text);
        } else {
          appendMessage('system', 'Un asesor te responderá en breve.');
        }
      })
      .catch(function (err) {
        appendMessage('system', 'No se pudo enviar: ' + (err.message || 'error'));
      })
      .finally(function () {
        state.sending = false;
        setSending(elements.chatForm, false);
      });
  }

  function ready(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  ready(function () {
    injectStyles();
    build();
  });
})();
