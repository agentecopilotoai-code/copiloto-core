import { useState } from 'react';

import {
  exportAuditLogs,
  exportTenantData,
  listAuditLogsFiltered,
  suppressContact,
} from '../../../../services/coreApi.js';
import { buildFilterPayload, emptyFilters } from '../auditData.js';

/**
 * Data layer for the Config · Auditoría view. Owns the audit-log query state,
 * the dense filter form and the privacy tools (contact suppression + tenant
 * data export), plus every handler extracted verbatim from the legacy
 * `AuditPanel` (including the native suppression confirm).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 */
export function useAuditData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [logs, setLogs] = useState([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [suppressId, setSuppressId] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [loaded, setLoaded] = useState(false);

  const actions = {
    setFilters,
    setSuppressId,
    dismissNotice: () => setNotice(null),
    async loadLogs() {
      if (!tenantId) return;
      setIsBusy(true);
      setNotice(null);
      try {
        const result = await listAuditLogsFiltered(
          session,
          tenantId,
          buildFilterPayload(filters),
        );
        setLogs(Array.isArray(result) ? result : []);
        setLoaded(true);
        if (!result || result.length === 0) {
          setNotice({ type: 'info', text: 'Sin registros para los filtros aplicados.' });
        }
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    exportCsv() {
      if (!tenantId) return;
      exportAuditLogs(session, tenantId, buildFilterPayload(filters, { includeLimit: false }));
    },
    async suppressContact() {
      const id = suppressId.trim();
      if (!id || !tenantId) {
        setNotice({ type: 'error', text: 'Ingresa el UUID del contacto a suprimir.' });
        return;
      }
      // Native confirm is preserved from the legacy module; UI-011 sweeps it.
      if (
        !window.confirm(
          `¿Confirmas suprimir el contacto ${id}? Esta acción anonimiza datos personales y no es reversible.`,
        )
      ) {
        return;
      }
      setIsBusy(true);
      setNotice(null);
      try {
        await suppressContact(session, tenantId, id);
        setSuppressId('');
        setNotice({
          type: 'success',
          text: `Contacto ${id} suprimido. Los datos personales han sido anonimizados y el evento queda en auditoría.`,
        });
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
    async exportTenantData() {
      if (!tenantId) return;
      setIsBusy(true);
      setNotice(null);
      try {
        await exportTenantData(session, tenantId);
      } catch (error) {
        setNotice({ type: 'error', text: error.message });
      } finally {
        setIsBusy(false);
      }
    },
  };

  return {
    state: { tenantId, logs, filters, suppressId, isBusy, notice, loaded },
    actions,
  };
}
