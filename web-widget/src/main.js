// Entry point bundled by Vite into dist/widget.js.
// Boot order: read config -> build API client -> mount DOM -> arm poller.
import './widget.css';
import { readConfig } from './config.js';
import { createApi } from './api.js';
import { createPoller } from './poller.js';
import { createState } from './state.js';
import { mountUi } from './ui.js';

function bootstrap() {
  if (window.__copilotoiaWidgetLoaded) return;
  const config = readConfig();
  if (!config) {
    // eslint-disable-next-line no-console
    console.warn('[copilotoia] Missing data-tenant or data-widget-token');
    return;
  }
  window.__copilotoiaWidgetLoaded = true;

  const state = createState();
  const api = createApi({
    apiBase: config.apiBase,
    getSessionToken: () => state.sessionToken,
  });

  let ui = null;
  const poller = createPoller({
    api,
    intervalMs: config.pollIntervalMs,
    onNewMessage: (m) => {
      if (!ui) return;
      if (m.direction === 'outbound') {
        ui.appendMessage(m.sender_actor_type === 'agent' ? 'bot' : 'bot', m.body_text);
      }
    },
  });

  ui = mountUi({ config, state, api, poller });
}

function ready(fn) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn);
  } else {
    fn();
  }
}

ready(bootstrap);
