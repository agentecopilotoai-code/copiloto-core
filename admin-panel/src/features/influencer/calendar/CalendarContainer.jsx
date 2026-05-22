/**
 * UI-INFLU-014 wiring — Container del calendario semanal de personajes.
 *
 * `Calendar.jsx` es presentacional: recibe `posts`, `personas`,
 * `currentDate` y callbacks (`onApprove`, `onReschedule`, `onCancel`).
 * Este container:
 *
 *   - Fetcha `GET /influencer/calendar?from&to&persona_id?` para el
 *     rango semanal centrado en `currentDate`.
 *   - Fetcha `GET /influencer/casting` (TASK-INFLU-017) para la lista
 *     de personas (para los filtros del sidebar del calendar).
 *   - Cablea `onApprove` → `PATCH /posts/{id}` con `status='approved'`.
 *   - Cablea `onCancel` → `POST /posts/{id}/cancel`.
 *   - Cablea `onReschedule` → `PATCH /posts/{id}` con `scheduled_at` nuevo
 *     (el componente abre un date-picker; este container solo recibe la
 *     nueva fecha en el callback).
 *
 * Es el componente que reemplaza al placeholder `InfluencerCalendar` de
 * `placeholders.jsx`. El `moduleRegistry` se actualiza para apuntar a
 * este componente.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useOutletContext } from 'react-router-dom';

import { LoadingScreen } from '../../../components/layout/LoadingScreen.jsx';
import { useAuth } from '../../../context/AuthContext.jsx';
import {
  cancelPost,
  getCalendar,
  getCasting,
  updatePost,
} from '../../../services/coreApi.js';
import { Calendar } from './Calendar.jsx';

/** Devuelve `{ from, to }` ISO date strings para la semana de `currentDate`. */
function weekRangeIso(currentDate) {
  const date = new Date(currentDate);
  const day = date.getDay(); // 0 = Sunday, 1 = Monday, ...
  // Semana lunes-domingo (estándar es-419). Si es domingo (0), -6; sino,
  // -((day - 1)).
  const mondayOffset = day === 0 ? -6 : 1 - day;
  const monday = new Date(date);
  monday.setDate(date.getDate() + mondayOffset);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);
  return {
    from: monday.toISOString().slice(0, 10),
    to: sunday.toISOString().slice(0, 10),
  };
}

export function CalendarContainer() {
  const { activeTenant } = useOutletContext() ?? {};
  const { session } = useAuth();
  const tenantId = activeTenant?.id;

  // Sin date picker propio en el componente; usamos la fecha actual.
  // UI-INFLU-014 follow-up: el componente puede emitir `onChangeWeek` y
  // refrescar el rango. Por ahora, semana actual.
  const currentDate = useMemo(() => new Date(), []);
  const range = useMemo(() => weekRangeIso(currentDate), [currentDate]);

  const [posts, setPosts] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!session || !tenantId) return undefined;
    let cancelled = false;
    setLoading(true);
    Promise.allSettled([
      getCalendar(session, tenantId, range),
      getCasting(session, tenantId),
    ]).then(([calRes, castRes]) => {
      if (cancelled) return;
      if (calRes.status === 'fulfilled') {
        setPosts(calRes.value?.posts ?? calRes.value ?? []);
      }
      if (castRes.status === 'fulfilled') {
        const list = castRes.value?.personas ?? [];
        setPersonas(list.map((p) => ({
          id: p.id,
          display_name: p.display_name || p.handle,
          handle: p.handle,
        })));
      }
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, range, refreshKey]);

  const refresh = useCallback(() => setRefreshKey((k) => k + 1), []);

  const handleApprove = useCallback(async (post) => {
    await updatePost(session, tenantId, post.id, { status: 'approved' });
    refresh();
  }, [session, tenantId, refresh]);

  const handleCancel = useCallback(async (post) => {
    await cancelPost(session, tenantId, post.id);
    refresh();
  }, [session, tenantId, refresh]);

  const handleReschedule = useCallback(async (post) => {
    // El componente abre un date-picker propio y emite `post` con
    // `scheduled_at` actualizado. Si no es el caso (sino solo el post
    // original), el container no puede saber a qué fecha mover — en
    // ese caso es no-op. UI-INFLU-014 follow-up para el date-picker.
    if (!post.scheduled_at) return;
    await updatePost(session, tenantId, post.id, {
      scheduled_at: post.scheduled_at,
    });
    refresh();
  }, [session, tenantId, refresh]);

  if (loading) return <LoadingScreen />;

  return (
    <Calendar
      posts={posts}
      personas={personas}
      currentDate={currentDate}
      onApprove={handleApprove}
      onCancel={handleCancel}
      onReschedule={handleReschedule}
    />
  );
}
