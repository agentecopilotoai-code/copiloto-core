import { useCallback, useEffect, useMemo, useState } from 'react';

import { listAppointments } from '../../../../services/coreApi.js';
import {
  deriveCounts,
  filterByDay,
  shiftDayISO,
  sortByTime,
  todayISO,
} from '../todayAppointmentsData.js';

/**
 * Capa de datos de la vista "Hoy · Citas del día". Posee el día seleccionado
 * (por defecto hoy), trae la lista completa de citas vía `listAppointments`
 * (tenant-scoped server-side) y aplica el filtro por día en cliente sobre el
 * campo `starts_at` — `listAppointments` no tiene un parámetro de fecha
 * establecido en el frontend, así que no se inventa uno.
 *
 * @param {object} options
 * @param {object} options.session — sesión admin (lleva el access token)
 * @param {object|undefined} options.tenant — tenant activo
 * @returns {{ state: object, actions: object }}
 */
export function useTodayAppointmentsData({ session, tenant }) {
  const tenantId = tenant?.id;

  const [selectedDay, setSelectedDay] = useState(todayISO);
  const [appointments, setAppointments] = useState([]);
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

    // BUG-044: pasar from_date/to_date al endpoint server-side. Antes el
    // filtro por día se aplicaba en cliente sobre las primeras 250 rows
    // sin filtro, y tenants con >250 citas perdían las del día actual.
    listAppointments(session, tenantId, { from_date: selectedDay, to_date: selectedDay })
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
    // BUG-044: re-fetch al cambiar de día (selectedDay es parte de la query).
  }, [session, tenantId, reloadToken, selectedDay]);

  const dayAppointments = useMemo(
    () => sortByTime(filterByDay(appointments, selectedDay)),
    [appointments, selectedDay],
  );
  const counts = useMemo(() => deriveCounts(dayAppointments), [dayAppointments]);

  const actions = {
    refresh,
    goToPrevDay: () => setSelectedDay((day) => shiftDayISO(day, -1)),
    goToNextDay: () => setSelectedDay((day) => shiftDayISO(day, 1)),
    goToToday: () => setSelectedDay(todayISO()),
  };

  return {
    state: {
      tenantId,
      selectedDay,
      dayAppointments,
      counts,
      isLoading,
      error,
    },
    actions,
  };
}
