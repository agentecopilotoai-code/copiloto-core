import { useCallback, useEffect, useMemo, useState } from 'react';

import { listAppointments } from '../../../../services/coreApi.js';
import {
  downloadCsv,
  filterAppointments,
  paginate,
  toCsv,
} from '../viewerAppointmentsData.js';

/** Tamaño de página por defecto del listado Viewer. */
export const DEFAULT_PAGE_SIZE = 10;

/** Estado inicial del formulario de filtros (todos vacíos = sin filtrar). */
function emptyFilters() {
  return { status: '', from: '', to: '', query: '' };
}

/**
 * UI-010.3 — capa de datos de la vista «Lectura · Citas» (Viewer).
 *
 * Owns el estado de filtros + página + lista cruda traída por
 * `listAppointments`. Aplica los filtros y la paginación en cliente con los
 * helpers puros de `viewerAppointmentsData.js`. `listAppointments` no expone
 * parámetros de fecha establecidos en el frontend — la lista es tenant-scoped
 * server-side, y el filtrado por status/rango/query corre en el cliente igual
 * que en la vista Agente "Hoy · Citas del día".
 *
 * `actions.exportCsv` corre sobre los registros filtrados (no sólo los
 * paginados) — el spec del backlog dice "export-to-CSV opcional" y exportar
 * únicamente la página visible sería contraintuitivo. La acción reusa los
 * helpers puros `toCsv` + `downloadCsv` (única ruta impura del feature).
 *
 * @param {object} options
 * @param {object} options.session — admin session (carries the access token)
 * @param {object|undefined} options.tenant — active tenant
 * @param {number} [options.pageSize=DEFAULT_PAGE_SIZE]
 * @returns {{ state: object, actions: object }}
 */
export function useViewerAppointmentsData({
  session,
  tenant,
  pageSize = DEFAULT_PAGE_SIZE,
}) {
  const tenantId = tenant?.id;

  const [appointments, setAppointments] = useState([]);
  const [filters, setFilters] = useState(emptyFilters);
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [reloadToken, setReloadToken] = useState(0);

  const refresh = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    if (!tenantId) {
      setAppointments([]);
      return undefined;
    }
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    listAppointments(session, tenantId)
      .then((items) => {
        if (cancelled) return;
        setAppointments(Array.isArray(items) ? items : []);
      })
      .catch((err) => {
        if (cancelled) return;
        setAppointments([]);
        setError(err?.message || 'No se pudieron cargar las citas.');
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session, tenantId, reloadToken]);

  const filtered = useMemo(
    () => filterAppointments(appointments, filters),
    [appointments, filters],
  );

  const paged = useMemo(
    () => paginate(filtered, page, pageSize),
    [filtered, page, pageSize],
  );

  const actions = {
    refresh,
    setFilter: (key, value) => {
      setFilters((prev) => ({ ...prev, [key]: value }));
      // Cuando cambia un filtro la paginación arranca de nuevo en la página 1.
      setPage(1);
    },
    resetFilters: () => {
      setFilters(emptyFilters());
      setPage(1);
    },
    setPage: (next) => setPage(next),
    exportCsv: () => {
      const csv = toCsv(filtered);
      downloadCsv(csv, 'citas.csv');
    },
  };

  return {
    state: {
      tenantId,
      filters,
      pageSize,
      page: paged.page,
      totalPages: paged.totalPages,
      // `total` es el tamaño de la lista cruda traída del servidor; `filteredCount`
      // es la cantidad después de aplicar filtros (sobre la que actúa la
      // paginación y la exportación CSV).
      total: appointments.length,
      pagedAppointments: paged.items,
      filteredCount: filtered.length,
      isLoading,
      error,
    },
    actions,
  };
}
