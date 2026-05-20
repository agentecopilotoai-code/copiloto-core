/**
 * UI-INFLU-014 — Calendario semanal de todos los personajes.
 */
import { useMemo, useState } from 'react';

import { Card, PageHeader, useConfirm } from '../../../components/ui/index.js';
import { usePermissions } from '../../../permissions/index.js';
import {
  canApprove as canApproveFn,
  formatTimeSlot,
  groupPostsByDay,
  personaColorMap,
  weekRange,
} from './calendarData.js';


const DAYS_ES = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];


export function Calendar({
  posts = [],
  personas = [],
  currentDate = new Date(),
  onReschedule,
  onCancel,
  onApprove,
}) {
  const permissions = usePermissions();
  const confirm = useConfirm();
  const [activePersonaIds, setActivePersonaIds] = useState(personas.map((p) => p.id));
  const [drawerPost, setDrawerPost] = useState(null);

  const range = useMemo(() => weekRange(currentDate), [currentDate]);
  const colorMap = useMemo(() => personaColorMap(personas), [personas]);
  const filteredPosts = useMemo(
    () => posts.filter((p) => activePersonaIds.includes(p.persona_id)),
    [posts, activePersonaIds],
  );
  const byDay = useMemo(() => groupPostsByDay(filteredPosts), [filteredPosts]);

  const togglePersona = (id) => {
    setActivePersonaIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  const handleCancel = async (post) => {
    const ok = await confirm({
      title: '¿Cancelar este post?',
      description: 'Esta acción no se puede deshacer.',
      confirmLabel: 'Cancelar post',
      cancelLabel: 'Volver',
    });
    if (ok) {
      await onCancel?.(post);
      setDrawerPost(null);
    }
  };

  const canApprove = canApproveFn(permissions);

  const weekDays = useMemo(() => {
    const out = [];
    const start = new Date(range.from);
    for (let i = 0; i < 7; i += 1) {
      const d = new Date(start);
      d.setDate(start.getDate() + i);
      out.push(d);
    }
    return out;
  }, [range.from]);

  return (
    <div data-module="influencer" data-view="calendar">
      <PageHeader eyebrow="Ravit Studio" title="Calendario" description={range.label} />

      <div role="toolbar" aria-label="Filtros de personajes" style={{
        display: 'flex', flexWrap: 'wrap', gap: 'var(--space-1)', marginBottom: 'var(--space-3)',
      }}>
        {personas.map((p) => {
          const active = activePersonaIds.includes(p.id);
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => togglePersona(p.id)}
              aria-pressed={active}
              style={{
                padding: '4px 10px', borderRadius: 999,
                border: '1px solid var(--color-border, #d1d5db)',
                background: active ? colorMap[p.id] : 'transparent',
                color: active ? '#fff' : 'inherit',
                cursor: 'pointer',
              }}
            >
              <span aria-hidden="true" style={{
                display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
                background: colorMap[p.id], marginRight: 6,
              }} />
              {p.name}
            </button>
          );
        })}
      </div>

      <Card padding="md">
        <table aria-label="Calendario semanal" style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              {weekDays.map((d, i) => (
                <th key={d.toISOString()} scope="col" style={{
                  textAlign: 'left', padding: 'var(--space-1)',
                  borderBottom: '1px solid var(--color-border-subtle, #e5e7eb)',
                  fontSize: 12, fontWeight: 600,
                }}>
                  {DAYS_ES[i]} {d.getDate()}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {weekDays.map((d) => {
                const key = d.toISOString().slice(0, 10);
                const dayPosts = byDay[key] || [];
                return (
                  <td key={key} style={{
                    verticalAlign: 'top', padding: 'var(--space-1)',
                    borderRight: '1px solid var(--color-border-subtle, #e5e7eb)',
                    height: 240,
                  }}>
                    {dayPosts.length === 0 && (
                      <span style={{ fontSize: 11, color: 'var(--color-text-subtle, #6b7280)' }}>
                        Sin posts
                      </span>
                    )}
                    {dayPosts.map((post) => (
                      <button
                        key={post.id}
                        type="button"
                        onClick={() => setDrawerPost(post)}
                        aria-label={`Post ${post.kind} a las ${formatTimeSlot(post.scheduled_at)}`}
                        style={{
                          display: 'block', width: '100%', textAlign: 'left',
                          padding: 'var(--space-1)', marginBottom: 4,
                          border: post.status === 'scheduled'
                            ? `2px dashed ${colorMap[post.persona_id] || '#999'}`
                            : `1px solid ${colorMap[post.persona_id] || '#ccc'}`,
                          borderRadius: 4,
                          background: 'transparent',
                          cursor: 'pointer',
                          fontSize: 12,
                        }}
                      >
                        <span aria-hidden="true" style={{
                          display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
                          background: colorMap[post.persona_id] || '#999', marginRight: 4,
                        }} />
                        {formatTimeSlot(post.scheduled_at)} · {post.kind}
                      </button>
                    ))}
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </Card>

      {drawerPost && (
        <aside aria-label="Detalle del post" style={{
          position: 'fixed', top: 0, right: 0, height: '100vh', width: 360,
          background: 'var(--color-surface, #fff)',
          borderLeft: '1px solid var(--color-border, #d1d5db)',
          padding: 'var(--space-3)',
          overflowY: 'auto',
          zIndex: 100,
        }}>
          <button
            type="button"
            onClick={() => setDrawerPost(null)}
            aria-label="Cerrar detalle"
            style={{ float: 'right' }}
          >×</button>
          <h2 style={{ marginTop: 0 }}>{drawerPost.kind}</h2>
          <div style={{ fontSize: 12, color: 'var(--color-text-subtle, #6b7280)' }}>
            {formatTimeSlot(drawerPost.scheduled_at)} · {drawerPost.platforms?.join(', ')}
          </div>
          <p>{drawerPost.caption}</p>
          <div style={{ display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap', marginTop: 'var(--space-3)' }}>
            <button
              type="button"
              onClick={() => onApprove?.(drawerPost)}
              disabled={!canApprove}
              title={canApprove ? undefined : 'No tienes permiso para aprobar+publicar'}
            >Aprobar y publicar</button>
            <button type="button" onClick={() => onReschedule?.(drawerPost)}>Reprogramar</button>
            <button type="button" onClick={() => handleCancel(drawerPost)}>Cancelar</button>
          </div>
        </aside>
      )}
    </div>
  );
}
