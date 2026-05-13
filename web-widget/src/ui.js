// DOM construction + event wiring. The CSS side-effect import lives in
// main.js so unit tests can load this module under plain Node.
import { readUtm } from './config.js';

function el(tag, attrs, children) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const key in attrs) {
      const val = attrs[key];
      if (val == null) continue;
      if (key === 'text') node.textContent = val;
      else if (key === 'html') node.innerHTML = val;
      else node.setAttribute(key, val);
    }
  }
  if (Array.isArray(children)) for (const c of children) if (c) node.appendChild(c);
  return node;
}

function applyTheme(root, config) {
  root.style.setProperty('--cpi-color', config.color);
  root.style.setProperty('--cpi-side', config.position === 'left' ? 'left' : 'right');
}

export function mountUi({ config, state, api, poller, onError }) {
  const root = el('div', { class: 'cpi-root' });
  applyTheme(root, config);

  const fab = el('button', {
    class: 'cpi-fab',
    type: 'button',
    'aria-label': 'Abrir chat',
    text: '💬',
  });

  const header = el('header', { class: 'cpi-header' }, [
    config.logoUrl
      ? el('img', { class: 'cpi-logo', src: config.logoUrl, alt: '' })
      : null,
    el('h3', { text: 'Asistente' }),
    el('button', { class: 'cpi-close', type: 'button', 'aria-label': 'Cerrar', text: '×' }),
  ]);

  const body = el('div', { class: 'cpi-body' });
  const leadForm = el('form', { class: 'cpi-form', 'data-form': 'lead' });
  leadForm.innerHTML =
    '<input type="text" name="name" placeholder="Nombre *" required maxlength="160"/>' +
    '<input type="tel" name="phone" placeholder="Teléfono (opcional)" maxlength="32"/>' +
    '<input type="email" name="email" placeholder="Email (opcional)" maxlength="320"/>' +
    '<textarea name="message" placeholder="¿En qué te ayudamos? *" required maxlength="4000"></textarea>' +
    '<button type="submit">Enviar</button>';

  const chatForm = el('form', { class: 'cpi-form cpi-form-chat', 'data-form': 'chat', style: 'display:none;' });
  chatForm.innerHTML =
    '<div class="cpi-row">' +
    '<textarea name="body" placeholder="Escribe tu mensaje..." required maxlength="4000"></textarea>' +
    '<button type="submit" aria-label="Enviar">➤</button>' +
    '</div>';

  const footer = el('div', { class: 'cpi-footer', text: 'Powered by CopilotoIA' });

  const panel = el('div', {
    class: 'cpi-panel',
    role: 'dialog',
    'aria-label': 'CopilotoIA chat',
    style: 'display:none;',
  }, [header, body, leadForm, chatForm, footer]);

  root.appendChild(fab);
  root.appendChild(panel);
  document.body.appendChild(root);

  function appendMessage(role, text) {
    if (!text) return;
    const msg = el('div', { class: 'cpi-msg ' + role, text });
    body.appendChild(msg);
    body.scrollTop = body.scrollHeight;
  }

  function toggle() {
    state.open = !state.open;
    panel.style.display = state.open ? 'flex' : 'none';
  }

  function setSending(form, sending) {
    const btn = form.querySelector('button[type="submit"]');
    if (btn) btn.disabled = sending;
  }

  fab.addEventListener('click', toggle);
  header.querySelector('.cpi-close').addEventListener('click', toggle);

  appendMessage('system', config.greeting);
  if (config.welcomeCopy) appendMessage('system', config.welcomeCopy);

  leadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (state.sending) return;
    const fd = new FormData(leadForm);
    const message = (fd.get('message') || '').toString().trim();
    const name = (fd.get('name') || '').toString().trim();
    if (!name || !message) return;
    const utm = readUtm();
    const payload = {
      tenant_slug: config.tenant,
      widget_token: config.widgetToken,
      name,
      phone: (fd.get('phone') || '').toString().trim() || undefined,
      email: (fd.get('email') || '').toString().trim() || undefined,
      message,
      utm_source: utm.utm_source,
      utm_medium: utm.utm_medium,
      utm_campaign: utm.utm_campaign,
      referrer: utm.referrer,
      referrer_contact_id: config.referrerContactId || undefined,
    };
    state.sending = true;
    setSending(leadForm, true);
    appendMessage('user', message);
    try {
      const data = await api.start(payload);
      state.sessionToken = data.session_token;
      state.conversationId = data.conversation_id;
      state.contactId = data.contact_id;
      state.started = true;
      const initialIds = [];
      if (data.inbound_message_id) initialIds.push(data.inbound_message_id);
      if (data.bot_reply) {
        if (data.bot_reply.id) initialIds.push(data.bot_reply.id);
        if (data.bot_reply.body_text) appendMessage('bot', data.bot_reply.body_text);
      }
      leadForm.style.display = 'none';
      chatForm.style.display = 'flex';
      chatForm.querySelector('textarea').focus();
      poller.start(data.conversation_id, { knownIds: initialIds });
    } catch (err) {
      appendMessage('system', 'No pudimos iniciar el chat: ' + (err.message || 'error'));
      if (onError) onError(err);
    } finally {
      state.sending = false;
      setSending(leadForm, false);
    }
  });

  chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (state.sending || !state.conversationId) return;
    const textarea = chatForm.querySelector('textarea');
    const value = (textarea.value || '').trim();
    if (!value) return;
    textarea.value = '';
    appendMessage('user', value);
    state.sending = true;
    setSending(chatForm, true);
    try {
      const data = await api.sendMessage(state.conversationId, value);
      if (data && data.inbound_message_id) poller.markSeen(data.inbound_message_id);
      if (data && data.bot_reply) {
        if (data.bot_reply.id) poller.markSeen(data.bot_reply.id);
        if (data.bot_reply.body_text) appendMessage('bot', data.bot_reply.body_text);
      }
    } catch (err) {
      appendMessage('system', 'No se pudo enviar: ' + (err.message || 'error'));
      if (onError) onError(err);
    } finally {
      state.sending = false;
      setSending(chatForm, false);
    }
  });

  return {
    root,
    panel,
    fab,
    appendMessage,
    toggle,
  };
}
