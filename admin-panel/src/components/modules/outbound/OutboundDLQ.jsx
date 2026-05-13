import { useEffect, useState } from 'react';

import { listOutboundDlq, retryOutboundDlqMessage } from '../../../services/coreApi.js';

function formatDate(value) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

function Notice({ notice }) {
  if (!notice) return null;
  return <p className={`notice ${notice.type}`}>{notice.text}</p>;
}

function MessageDetail({ item, onClose }) {
  if (!item) return null;
  return (
    <div className="modal-overlay" onClick={onClose} role="presentation">
      <div className="modal-card" onClick={(event) => event.stopPropagation()} role="dialog">
        <header className="modal-header">
          <h3>Detalle del mensaje {item.id.slice(0, 8)}…</h3>
          <button className="modal-close" onClick={onClose} type="button" aria-label="Cerrar">
            ×
          </button>
        </header>
        <dl className="modal-body">
          <dt>error_code</dt>
          <dd>{item.error_code}</dd>
          <dt>error_message</dt>
          <dd className="mono">{item.error_message || '—'}</dd>
          <dt>failed_at</dt>
          <dd>{formatDate(item.failed_at)}</dd>
          <dt>message_type</dt>
          <dd>{item.message_type || '—'}</dd>
          <dt>body_preview</dt>
          <dd className="mono">{item.body_preview || '—'}</dd>
          <dt>payload</dt>
          <dd>
            <pre className="payload-block">{JSON.stringify(item.payload, null, 2)}</pre>
          </dd>
        </dl>
      </div>
    </div>
  );
}

export function OutboundDLQ({ module, session, tenant }) {
  const [items, setItems] = useState([]);
  const [totals, setTotals] = useState([]);
  const [errorCodeFilter, setErrorCodeFilter] = useState('');
  const [selected, setSelected] = useState(null);
  const [retryingId, setRetryingId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  async function loadDlq(filter = errorCodeFilter) {
    if (!tenant?.id) return;
    setIsLoading(true);
    setNotice(null);
    try {
      const result = await listOutboundDlq(session, tenant.id, {
        errorCode: filter || undefined,
        limit: 100,
      });
      setItems(result?.items || []);
      setTotals(result?.totals_by_error_code || []);
      if (!result?.items?.length) {
        setNotice({ type: 'info', text: 'Sin mensajes en la DLQ outbound para los filtros aplicados.' });
      }
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo cargar la DLQ.' });
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadDlq('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  function handleFilterClick(code) {
    const next = errorCodeFilter === code ? '' : code;
    setErrorCodeFilter(next);
    loadDlq(next);
  }

  async function handleRetry(item) {
    if (!tenant?.id) return;
    if (!window.confirm(`¿Reintentar envío del mensaje ${item.id.slice(0, 8)}…? Volverá a la cola del worker.`)) {
      return;
    }
    setRetryingId(item.id);
    setNotice(null);
    try {
      await retryOutboundDlqMessage(session, tenant.id, item.id);
      setNotice({ type: 'success', text: `Mensaje ${item.id.slice(0, 8)}… reencolado.` });
      await loadDlq(errorCodeFilter);
    } catch (error) {
      setNotice({ type: 'error', text: error.message || 'No se pudo reintentar el envío.' });
    } finally {
      setRetryingId(null);
    }
  }

  return (
    <section className="module-card" data-module="outbound-dlq">
      <header className="module-header">
        <div>
          <h2>{module?.label || 'Outbound DLQ'}</h2>
          <p className="hint">
            Mensajes que el event_worker no logró entregar a Meta. Filtra por código
            de error, revisa el detalle y reintenta el envío cuando la causa esté
            resuelta (token rotado, ventana 24h, etc.).
          </p>
        </div>
        <button className="ghost-action" onClick={() => loadDlq(errorCodeFilter)} type="button" disabled={isLoading}>
          {isLoading ? 'Cargando…' : 'Refrescar'}
        </button>
      </header>

      <Notice notice={notice} />

      <div className="dlq-totals">
        <h3>Errores agrupados</h3>
        {totals.length === 0 ? (
          <p className="hint">Sin fallos registrados en este tenant.</p>
        ) : (
          <ul className="dlq-totals-list">
            {totals.map((group) => (
              <li key={group.error_code}>
                <button
                  type="button"
                  className={`chip ${errorCodeFilter === group.error_code ? 'chip-active' : ''}`}
                  onClick={() => handleFilterClick(group.error_code)}
                  data-error-code={group.error_code}
                >
                  <strong>{group.error_code}</strong>
                  <span>{group.count}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="dlq-table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>error_code</th>
              <th>failed_at</th>
              <th>tipo</th>
              <th>preview</th>
              <th>acción</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id} data-message-id={item.id}>
                <td className="mono">
                  <button
                    type="button"
                    className="link-button"
                    onClick={() => setSelected(item)}
                  >
                    {item.id.slice(0, 8)}…
                  </button>
                </td>
                <td>{item.error_code}</td>
                <td>{formatDate(item.failed_at)}</td>
                <td>{item.message_type || '—'}</td>
                <td className="mono truncate">{item.body_preview || '—'}</td>
                <td>
                  <button
                    type="button"
                    className="primary-action small"
                    onClick={() => handleRetry(item)}
                    disabled={retryingId === item.id}
                    data-action="retry"
                  >
                    {retryingId === item.id ? 'Reintentando…' : 'Reintentar'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <MessageDetail item={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
