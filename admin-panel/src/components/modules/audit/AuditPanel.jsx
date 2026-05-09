import { useState } from 'react';

import {
  exportAuditLogs,
  exportTenantData,
  listAuditLogsFiltered,
  suppressContact,
} from '../../../services/coreApi.js';

function formatDate(value) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('es-CO', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value));
}

function Notice({ notice }) {
  if (!notice) return null;
  return <p className={`notice ${notice.type}`}>{notice.text}</p>;
}

export function AuditPanel({ module, session, tenant }) {
  const [logs, setLogs] = useState([]);
  const [filters, setFilters] = useState({ action: '', actorType: '', entityType: '', fromDate: '', toDate: '', limit: '200' });
  const [suppressId, setSuppressId] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [loaded, setLoaded] = useState(false);

  async function handleLoadLogs(event) {
    event.preventDefault();
    if (!tenant?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      const result = await listAuditLogsFiltered(session, tenant.id, {
        action: filters.action || undefined,
        actor_type: filters.actorType || undefined,
        entity_type: filters.entityType || undefined,
        from_date: filters.fromDate || undefined,
        to_date: filters.toDate || undefined,
        limit: filters.limit || '200',
      });
      setLogs(result);
      setLoaded(true);
      if (result.length === 0) setNotice({ type: 'info', text: 'Sin registros para los filtros aplicados.' });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  function handleExportCsv() {
    if (!tenant?.id) return;
    exportAuditLogs(session, tenant.id, {
      action: filters.action || undefined,
      actor_type: filters.actorType || undefined,
      entity_type: filters.entityType || undefined,
      from_date: filters.fromDate || undefined,
      to_date: filters.toDate || undefined,
    });
  }

  async function handleSuppressContact(event) {
    event.preventDefault();
    const id = suppressId.trim();
    if (!id || !tenant?.id) {
      setNotice({ type: 'error', text: 'Ingresa el UUID del contacto a suprimir.' });
      return;
    }
    if (!window.confirm(`¿Confirmas suprimir el contacto ${id}? Esta acción anonimiza datos personales y no es reversible.`)) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await suppressContact(session, tenant.id, id);
      setSuppressId('');
      setNotice({ type: 'success', text: `Contacto ${id} suprimido. Los datos personales han sido anonimizados y el evento queda en auditoría.` });
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  async function handleExportTenantData() {
    if (!tenant?.id) return;
    setIsBusy(true);
    setNotice(null);
    try {
      await exportTenantData(session, tenant.id);
    } catch (error) {
      setNotice({ type: 'error', text: error.message });
    } finally {
      setIsBusy(false);
    }
  }

  return (
    <section className="module-card audit-panel">
      <div className="module-heading">
        <div>
          <p className="eyebrow">{module.label}</p>
          <h2>Auditoría y privacidad</h2>
          <p className="hint">{module.summary}</p>
        </div>
      </div>

      <Notice notice={notice} />

      <div className="audit-section">
        <strong>Audit logs</strong>
        <p className="hint">Consulta y exporta el registro inmutable de acciones por tenant. Los filtros son acumulativos.</p>

        <form className="audit-filter-form" onSubmit={handleLoadLogs}>
          <label>
            Acción
            <input
              onChange={(e) => setFilters({ ...filters, action: e.target.value })}
              placeholder="quote.created, contact.suppressed…"
              value={filters.action}
            />
          </label>
          <label>
            Tipo de actor
            <select
              onChange={(e) => setFilters({ ...filters, actorType: e.target.value })}
              value={filters.actorType}
            >
              <option value="">Todos</option>
              <option value="user">user</option>
              <option value="agent">agent</option>
              <option value="bot">bot</option>
              <option value="service">service</option>
              <option value="system">system</option>
              <option value="support">support</option>
              <option value="contact">contact</option>
            </select>
          </label>
          <label>
            Tipo de entidad
            <input
              onChange={(e) => setFilters({ ...filters, entityType: e.target.value })}
              placeholder="tenant, contact, quote…"
              value={filters.entityType}
            />
          </label>
          <label>
            Desde
            <input
              onChange={(e) => setFilters({ ...filters, fromDate: e.target.value })}
              type="datetime-local"
              value={filters.fromDate}
            />
          </label>
          <label>
            Hasta
            <input
              onChange={(e) => setFilters({ ...filters, toDate: e.target.value })}
              type="datetime-local"
              value={filters.toDate}
            />
          </label>
          <label>
            Límite
            <input
              max="1000"
              min="1"
              onChange={(e) => setFilters({ ...filters, limit: e.target.value })}
              type="number"
              value={filters.limit}
            />
          </label>
          <div className="audit-filter-actions">
            <button className="primary-action" disabled={isBusy || !tenant?.id} type="submit">
              Consultar
            </button>
            <button className="secondary-action" disabled={isBusy || !tenant?.id} onClick={handleExportCsv} type="button">
              Exportar CSV
            </button>
          </div>
        </form>

        {loaded && (
          <div className="audit-table-wrap">
            <table className="audit-table">
              <thead>
                <tr>
                  <th>Fecha</th>
                  <th>Actor</th>
                  <th>Acción</th>
                  <th>Entidad</th>
                  <th>ID entidad</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr key={log.id}>
                    <td><time>{formatDate(log.created_at)}</time></td>
                    <td><span className="actor-chip">{log.actor_type}</span></td>
                    <td><code>{log.action}</code></td>
                    <td>{log.entity_type}</td>
                    <td><small>{log.entity_id}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {logs.length === 0 && <p className="hint">Sin resultados.</p>}
          </div>
        )}
      </div>

      <div className="audit-section privacy-section">
        <strong>Supresión de contacto (GDPR / derecho al olvido)</strong>
        <p className="hint">
          Anonimiza irreversiblemente los datos personales de un contacto: nombre, teléfono y WA ID son sustituidos por
          seudónimos; el contacto queda con estado <code>suppressed</code>. La acción queda registrada en auditoría.
        </p>
        <form className="schedule-form" onSubmit={handleSuppressContact}>
          <label className="wide">
            UUID del contacto
            <input
              onChange={(e) => setSuppressId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              value={suppressId}
            />
          </label>
          <button className="danger-action" disabled={isBusy || !suppressId.trim()} type="submit">
            Suprimir contacto
          </button>
        </form>
      </div>

      <div className="audit-section">
        <strong>Exportación de datos del tenant</strong>
        <p className="hint">
          Genera un archivo JSON con la configuración del tenant, ajustes de privacidad, canales activos y conteos
          de datos operativos. No incluye mensajes ni datos personales en texto claro.
        </p>
        <button className="secondary-action" disabled={isBusy || !tenant?.id} onClick={handleExportTenantData} type="button">
          Descargar datos del tenant
        </button>
      </div>

      <div className="audit-section dpa-section">
        <strong>Política de datos (DPA)</strong>
        <ul className="dpa-list">
          <li><strong>No entrenamiento:</strong> Los datos de conversaciones nunca se usan para entrenar modelos de IA. El campo <code>no_train</code> del tenant es <code>true</code> por defecto.</li>
          <li><strong>Retención:</strong> Los datos operativos se retienen máximo 365 días desde la última actividad del tenant. Los audit logs se conservan 730 días para cumplimiento.</li>
          <li><strong>PII en logs:</strong> Los logs de sistema redactan automáticamente teléfonos y correos antes de persistirlos.</li>
          <li><strong>Derecho al olvido:</strong> La supresión de contacto anonimiza datos personales de forma irreversible en menos de 24 horas desde la solicitud.</li>
          <li><strong>Procesador de datos:</strong> CopilotoIA actúa como encargado del tratamiento; el tenant es el responsable. Ver <code>docs/DPA.md</code> para el texto completo.</li>
        </ul>
      </div>
    </section>
  );
}
