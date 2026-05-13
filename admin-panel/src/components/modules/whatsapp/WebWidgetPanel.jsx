import { useEffect, useState } from 'react';

import { getWebChannel, upsertWebChannel } from '../../../services/coreApi.js';

function defaultForm() {
  return {
    enabled: true,
    allowed_origins: '',
    primary_color: '#1f7ae0',
    greeting: 'Hola 👋, ¿en qué te podemos ayudar?',
    logo_url: '',
    welcome_copy: '',
    button_position: 'right',
  };
}

function originsToList(text) {
  return text
    .split(/[\n,]/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function originsToText(list) {
  return Array.isArray(list) ? list.join('\n') : '';
}

export function WebWidgetPanel({ session, tenant }) {
  const tenantId = tenant?.id;
  const [form, setForm] = useState(defaultForm());
  const [snapshot, setSnapshot] = useState(null);
  const [notice, setNotice] = useState(null);
  const [isBusy, setIsBusy] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    setNotice(null);
    setSnapshot(null);
    setForm(defaultForm());
    if (!tenantId) return undefined;
    setIsLoading(true);
    getWebChannel(session, tenantId)
      .then((data) => {
        if (!mounted) return;
        setSnapshot(data);
        if (data?.channel) {
          const widgetConfig = data.channel.widget_config || {};
          setForm({
            enabled: data.channel.status === 'active',
            allowed_origins: originsToText(data.channel.allowed_origins || []),
            primary_color: widgetConfig.primary_color || '#1f7ae0',
            greeting: widgetConfig.greeting || 'Hola 👋, ¿en qué te podemos ayudar?',
            logo_url: widgetConfig.logo_url || '',
            welcome_copy: widgetConfig.welcome_copy || '',
            button_position: widgetConfig.button_position === 'left' ? 'left' : 'right',
          });
        }
      })
      .catch((err) => {
        if (!mounted || err.status === 404) return;
        setNotice({ type: 'error', text: err.message });
      })
      .finally(() => {
        if (mounted) setIsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [tenantId, session]);

  function updateField(key, value) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function saveChannel(rotateToken) {
    if (!tenantId) return;
    setIsBusy(true);
    setNotice(null);
    try {
      const payload = {
        enabled: Boolean(form.enabled),
        allowed_origins: originsToList(form.allowed_origins),
        primary_color: form.primary_color || null,
        greeting: form.greeting || null,
        logo_url: form.logo_url ? form.logo_url.trim() : null,
        welcome_copy: form.welcome_copy ? form.welcome_copy.trim() : null,
        button_position: form.button_position === 'left' ? 'left' : 'right',
        rotate_widget_token: Boolean(rotateToken),
      };
      const data = await upsertWebChannel(session, tenantId, payload);
      setSnapshot(data);
      setNotice({
        type: 'success',
        text: rotateToken ? 'Widget token rotado y canal guardado.' : 'Canal web guardado.',
      });
    } catch (err) {
      setNotice({ type: 'error', text: err.message });
    } finally {
      setIsBusy(false);
    }
  }

  function copySnippet() {
    const snippet = snapshot?.snippet;
    if (!snippet) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard
        .writeText(snippet)
        .then(() => setNotice({ type: 'success', text: 'Snippet copiado al portapapeles.' }))
        .catch(() => setNotice({ type: 'error', text: 'No se pudo copiar.' }));
    } else {
      setNotice({ type: 'error', text: 'Clipboard no disponible; copia manualmente.' });
    }
  }

  const channel = snapshot?.channel;
  const snippet = snapshot?.snippet;
  const hasToken = Boolean(snapshot?.has_widget_token);

  return (
    <div className="wizard-panel form-grid" style={{ gap: 12 }}>
      <div>
        <p className="eyebrow">Widget Web</p>
        <h3>Captura de leads desde sitio web</h3>
        <p className="hint">
          Habilita un chat flotante embebible que crea contacto y conversación en CopilotoIA,
          enrutadas al mismo orquestador RAG que WhatsApp. El widget incluye un formulario de
          captura (nombre + mensaje, teléfono y email opcionales) y registra UTMs en{' '}
          <code>lead_source</code>.
        </p>
      </div>

      {notice ? <p className={`notice ${notice.type}`}>{notice.text}</p> : null}
      {isLoading ? <p className="notice info">Cargando canal web…</p> : null}

      <label>
        <input
          checked={form.enabled}
          onChange={(event) => updateField('enabled', event.target.checked)}
          type="checkbox"
        />
        {' '}Canal web activo
      </label>

      <label className="wide">
        Dominios permitidos (uno por línea o separados por coma)
        <textarea
          onChange={(event) => updateField('allowed_origins', event.target.value)}
          placeholder="https://mi-negocio.com&#10;https://www.mi-negocio.com"
          rows={3}
          value={form.allowed_origins}
        />
        <small>
          Dejar vacío permite cualquier origen (útil sólo para pruebas). En producción registra
          los dominios donde se embebe el widget.
        </small>
      </label>

      <label>
        Color primario
        <input
          onChange={(event) => updateField('primary_color', event.target.value)}
          pattern="^#[0-9a-fA-F]{6}$"
          placeholder="#1f7ae0"
          type="text"
          value={form.primary_color}
        />
      </label>

      <label className="wide">
        Mensaje de bienvenida
        <input
          maxLength={500}
          onChange={(event) => updateField('greeting', event.target.value)}
          placeholder="Hola 👋, ¿en qué te podemos ayudar?"
          type="text"
          value={form.greeting}
        />
      </label>

      <label className="wide">
        Logo (URL pública)
        <input
          maxLength={2048}
          onChange={(event) => updateField('logo_url', event.target.value)}
          placeholder="https://cdn.tu-negocio.com/logo.png"
          type="url"
          value={form.logo_url}
        />
        <small>Opcional. Se muestra en la cabecera del panel del chat.</small>
      </label>

      <label className="wide">
        Copy secundario (subtítulo de bienvenida)
        <input
          maxLength={500}
          onChange={(event) => updateField('welcome_copy', event.target.value)}
          placeholder="Atendemos de lunes a viernes 9 a 18."
          type="text"
          value={form.welcome_copy}
        />
      </label>

      <label>
        Posición del botón
        <select
          onChange={(event) => updateField('button_position', event.target.value)}
          value={form.button_position}
        >
          <option value="right">Inferior derecha</option>
          <option value="left">Inferior izquierda</option>
        </select>
      </label>

      <div className="form-actions split-actions">
        <button
          className="secondary-action"
          disabled={isBusy || !tenantId}
          onClick={() => saveChannel(true)}
          type="button"
        >
          {hasToken ? 'Rotar widget token y guardar' : 'Generar widget token'}
        </button>
        <button
          className="primary-action"
          disabled={isBusy || !tenantId}
          onClick={() => saveChannel(false)}
          type="button"
        >
          Guardar canal web
        </button>
      </div>

      <div className="builder-preview">
        <strong>Snippet embebible</strong>
        {snippet ? (
          <>
            <pre>{snippet}</pre>
            <button
              className="secondary-action"
              disabled={!snippet}
              onClick={copySnippet}
              type="button"
            >
              Copiar al portapapeles
            </button>
          </>
        ) : (
          <p className="hint">
            Guarda el canal para generar el widget token y el snippet listo para pegar en el HTML
            del sitio.
          </p>
        )}
      </div>

      {channel ? (
        <div className="context-grid health-grid">
          <div>
            <dt>Estado</dt>
            <dd>{channel.status === 'active' ? 'Activo' : 'Suspendido'}</dd>
          </div>
          <div>
            <dt>Orígenes permitidos</dt>
            <dd>{(channel.allowed_origins || []).length || 'sin restricción'}</dd>
          </div>
          <div>
            <dt>Widget token</dt>
            <dd>{hasToken ? 'Configurado' : 'Falta'}</dd>
          </div>
          <div>
            <dt>Tenant slug</dt>
            <dd>{snapshot?.tenant_slug || '—'}</dd>
          </div>
        </div>
      ) : null}
    </div>
  );
}
