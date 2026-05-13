// Entry point bundled by Vite into dist/widget.js.
// Boot order: read config -> inject sibling stylesheet -> build API client ->
// mount DOM -> arm poller.
//
// The `import './widget.css'` below tells Vite (cssCodeSplit: false) to emit
// a separate widget.css file alongside widget.js. Vite does NOT auto-load it
// at runtime when the bundle is an IIFE served via <script>, so we inject a
// <link rel="stylesheet"> at boot pointing at the sibling on the same CDN
// path. Without this the FAB/panel would render unstyled.
import './widget.css';
import { readConfig } from './config.js';
import { createApi } from './api.js';
import { createPoller } from './poller.js';
import { createState } from './state.js';
import { mountUi } from './ui.js';

const CSS_LINK_ID = 'cpi-widget-css';

function injectStylesheet(assetBase) {
  if (!assetBase) return;
  if (document.getElementById(CSS_LINK_ID)) return;
  const href = assetBase.replace(/\/$/, '') + '/widget.css';
  const link = document.createElement('link');
  link.id = CSS_LINK_ID;
  link.rel = 'stylesheet';
  link.href = href;
  // Place it at the very end of <head> so customer CSS keeps precedence on
  // shared selectors; our styles are namespaced under .cpi-*.
  (document.head || document.documentElement).appendChild(link);
}

function bootstrap() {
  if (window.__copilotoiaWidgetLoaded) return;
  const config = readConfig();
  if (!config) {
    // eslint-disable-next-line no-console
    console.warn('[copilotoia] Missing data-tenant or data-widget-token');
    return;
  }
  window.__copilotoiaWidgetLoaded = true;
  injectStylesheet(config.assetBase);

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
