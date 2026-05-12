import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  getAnalyticsAppointments,
  getAnalyticsCampaigns,
  getAnalyticsContacts,
  getAnalyticsConversations,
  getAnalyticsFunnel,
  getAnalyticsOverview,
  getAnalyticsReferrals,
} from '../../../services/coreApi.js';

const SUB_TABS = [
  { id: 'overview', label: 'Resumen' },
  { id: 'funnel', label: 'Funnel' },
  { id: 'campaigns', label: 'Campañas' },
];

const FUNNEL_STEP_LABELS = {
  leads: 'Leads',
  engaged: 'Engaged',
  appointments_scheduled: 'Citas agendadas',
  appointments_completed: 'Citas completadas',
  repeat_customers: 'Clientes recurrentes',
};

const RANGE_PRESETS = [
  { id: '7d', label: '7 días', days: 7 },
  { id: '30d', label: '30 días', days: 30 },
  { id: '90d', label: '90 días', days: 90 },
  { id: 'custom', label: 'Personalizado', days: null },
];

const WEEKDAY_LABELS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
const STATUS_LABELS = {
  open: 'Abiertas',
  waiting_user: 'Esperando usuario',
  waiting_agent: 'Esperando agente',
  human_required: 'Handoff requerido',
  human_active: 'Con agente humano',
  resolved: 'Resueltas',
  closed: 'Cerradas',
  archived: 'Archivadas',
  scheduled: 'Programada',
  confirmed: 'Confirmada',
  completed: 'Completada',
  cancelled: 'Cancelada',
  no_show: 'No-show',
};

function toISODate(value) {
  return value.toISOString().slice(0, 10);
}

function defaultRange(days) {
  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - (days - 1));
  return { fromDate: toISODate(start), toDate: toISODate(today) };
}

function formatNumber(value) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('es-CO').format(value);
}

function formatCurrency(value) {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value) {
  if (value === null || value === undefined) return '-';
  return `${value.toFixed(1)}%`;
}

function MiniBars({ series, getValue, getLabel, height = 80 }) {
  const max = Math.max(1, ...series.map((row) => getValue(row) || 0));
  return (
    <div className="analytics-bars" style={{ height: `${height}px` }}>
      {series.map((row, idx) => {
        const value = getValue(row) || 0;
        const heightPct = (value / max) * 100;
        return (
          <div
            className="analytics-bar"
            key={getLabel(row, idx)}
            title={`${getLabel(row, idx)}: ${value}`}
          >
            <div className="analytics-bar-fill" style={{ height: `${heightPct}%` }} />
          </div>
        );
      })}
    </div>
  );
}

function Notice({ notice }) {
  if (!notice) return null;
  return <p className={`notice ${notice.type}`}>{notice.text}</p>;
}

export function AnalyticsPanel({ module, session, tenant }) {
  const [preset, setPreset] = useState('30d');
  const [range, setRange] = useState(() => defaultRange(30));
  const [activeTab, setActiveTab] = useState('overview');
  const [overview, setOverview] = useState(null);
  const [conversations, setConversations] = useState(null);
  const [appointments, setAppointments] = useState(null);
  const [contacts, setContacts] = useState(null);
  const [funnel, setFunnel] = useState(null);
  const [campaigns, setCampaigns] = useState(null);
  const [referrals, setReferrals] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [notice, setNotice] = useState(null);

  const tenantId = tenant?.id;

  const loadAll = useCallback(
    async (rng) => {
      if (!tenantId) return;
      setIsLoading(true);
      setNotice(null);
      try {
        const [ov, conv, appt, ctc, fnl, cmp, refs] = await Promise.all([
          getAnalyticsOverview(session, tenantId, rng),
          getAnalyticsConversations(session, tenantId, rng),
          getAnalyticsAppointments(session, tenantId, rng),
          getAnalyticsContacts(session, tenantId, rng),
          getAnalyticsFunnel(session, tenantId, rng),
          getAnalyticsCampaigns(session, tenantId, rng),
          getAnalyticsReferrals(session, tenantId, rng),
        ]);
        setOverview(ov);
        setConversations(conv);
        setAppointments(appt);
        setContacts(ctc);
        setFunnel(fnl);
        setCampaigns(cmp);
        setReferrals(refs);
      } catch (error) {
        setNotice({ type: 'error', text: error.message || 'No se pudieron cargar las métricas.' });
      } finally {
        setIsLoading(false);
      }
    },
    [session, tenantId],
  );

  useEffect(() => {
    loadAll(range);
  }, [loadAll, range]);

  function handlePresetChange(nextPreset) {
    setPreset(nextPreset);
    if (nextPreset !== 'custom') {
      const found = RANGE_PRESETS.find((p) => p.id === nextPreset);
      if (found?.days) setRange(defaultRange(found.days));
    }
  }

  function handleCustomChange(key, value) {
    setRange((prev) => ({ ...prev, [key]: value }));
  }

  const dailyConversations = useMemo(
    () => conversations?.daily_evolution ?? [],
    [conversations],
  );
  const dailyAppointments = useMemo(
    () => appointments?.daily_evolution ?? [],
    [appointments],
  );

  return (
    <section className="module-card analytics-panel">
      <div className="module-heading">
        <div>
          <p className="eyebrow">{module.label}</p>
          <h2>Analítica del negocio</h2>
          <p className="hint">{module.summary}</p>
        </div>
      </div>

      <Notice notice={notice} />

      <div className="analytics-filters">
        <div className="analytics-presets" role="tablist">
          {RANGE_PRESETS.map((option) => (
            <button
              className={`analytics-preset${preset === option.id ? ' active' : ''}`}
              key={option.id}
              onClick={() => handlePresetChange(option.id)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
        {preset === 'custom' && (
          <div className="analytics-custom-range">
            <label>
              Desde
              <input
                onChange={(e) => handleCustomChange('fromDate', e.target.value)}
                type="date"
                value={range.fromDate || ''}
              />
            </label>
            <label>
              Hasta
              <input
                onChange={(e) => handleCustomChange('toDate', e.target.value)}
                type="date"
                value={range.toDate || ''}
              />
            </label>
            <button
              className="secondary-action"
              disabled={isLoading || !tenantId}
              onClick={() => loadAll(range)}
              type="button"
            >
              Aplicar
            </button>
          </div>
        )}
        <button
          className="secondary-action"
          disabled={isLoading || !tenantId}
          onClick={() => loadAll(range)}
          type="button"
        >
          {isLoading ? 'Actualizando…' : 'Actualizar'}
        </button>
      </div>

      {!tenantId && <p className="hint">Selecciona un tenant para ver sus métricas.</p>}

      {tenantId && (
        <div className="analytics-subtabs" role="tablist">
          {SUB_TABS.map((tab) => (
            <button
              className={`analytics-subtab${activeTab === tab.id ? ' active' : ''}`}
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              type="button"
            >
              {tab.label}
            </button>
          ))}
        </div>
      )}

      {tenantId && activeTab === 'funnel' && (
        <FunnelView funnel={funnel} isLoading={isLoading} />
      )}

      {tenantId && activeTab === 'campaigns' && (
        <CampaignsView campaigns={campaigns} isLoading={isLoading} />
      )}

      {tenantId && activeTab === 'overview' && overview && (
        <>
          <div className="analytics-kpis">
            <div className="kpi-card">
              <p className="kpi-label">Conversaciones</p>
              <p className="kpi-value">{formatNumber(overview.conversations.total)}</p>
              <p className="kpi-hint">
                {formatNumber(overview.conversations.resolved)} resueltas ·{' '}
                {formatPercent(overview.conversations.handoff_rate_pct)} handoff
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Citas completadas</p>
              <p className="kpi-value">{formatNumber(overview.appointments.completed)}</p>
              <p className="kpi-hint">
                {formatNumber(overview.appointments.created)} creadas ·{' '}
                {formatNumber(overview.appointments.cancelled)} canceladas
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Tasa de no-show</p>
              <p className="kpi-value">{formatPercent(overview.appointments.no_show_rate_pct)}</p>
              <p className="kpi-hint">
                {formatNumber(overview.appointments.no_shows)} no-shows
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Ingreso estimado</p>
              <p className="kpi-value">{formatCurrency(overview.revenue.estimated_amount)}</p>
              <p className="kpi-hint">Sólo citas completadas</p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Calificación promedio</p>
              <p className="kpi-value">
                {overview.feedback.ratings_count
                  ? overview.feedback.average_rating.toFixed(2)
                  : '-'}
              </p>
              <p className="kpi-hint">
                {formatNumber(overview.feedback.ratings_count)} calificaciones
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Retención (90 días)</p>
              <p className="kpi-value">{formatPercent(overview.retention.retention_rate_pct)}</p>
              <p className="kpi-hint">
                {formatNumber(overview.retention.recurring_contacts)} contactos recurrentes
              </p>
            </div>
            <div className="kpi-card">
              <p className="kpi-label">Mensajes</p>
              <p className="kpi-value">
                {formatNumber(
                  (overview.messages.inbound || 0) + (overview.messages.outbound || 0),
                )}
              </p>
              <p className="kpi-hint">
                {formatNumber(overview.messages.inbound)} entrantes ·{' '}
                {formatNumber(overview.messages.outbound)} salientes
              </p>
            </div>
          </div>

          <div className="analytics-grid">
            <div className="analytics-card">
              <h3>Evolución diaria de conversaciones</h3>
              {dailyConversations.length === 0 ? (
                <p className="hint">Sin datos para el rango seleccionado.</p>
              ) : (
                <>
                  <MiniBars
                    getLabel={(row) => row.date}
                    getValue={(row) => row.count}
                    series={dailyConversations}
                  />
                  <div className="analytics-bars-axis">
                    <span>{dailyConversations[0]?.date}</span>
                    <span>{dailyConversations[dailyConversations.length - 1]?.date}</span>
                  </div>
                </>
              )}
            </div>

            <div className="analytics-card">
              <h3>Evolución diaria de citas</h3>
              {dailyAppointments.length === 0 ? (
                <p className="hint">Sin datos para el rango seleccionado.</p>
              ) : (
                <table className="analytics-table compact">
                  <thead>
                    <tr>
                      <th>Día</th>
                      <th>Creadas</th>
                      <th>Completadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dailyAppointments.map((row) => (
                      <tr key={row.date}>
                        <td><time>{row.date}</time></td>
                        <td>{formatNumber(row.created)}</td>
                        <td>{formatNumber(row.completed)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="analytics-card">
              <h3>Origen de leads (lead_source.channel)</h3>
              {(overview.lead_sources ?? []).length === 0 ? (
                <p className="hint">Aún no se registran contactos en el rango seleccionado.</p>
              ) : (
                <table className="analytics-table">
                  <thead>
                    <tr>
                      <th>Canal</th>
                      <th>Contactos</th>
                      <th>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const total = overview.lead_sources.reduce((sum, row) => sum + (row.count || 0), 0);
                      return overview.lead_sources.map((row) => (
                        <tr key={row.channel}>
                          <td><code>{row.channel}</code></td>
                          <td>{formatNumber(row.count)}</td>
                          <td>{formatPercent(total ? (row.count / total) * 100 : 0)}</td>
                        </tr>
                      ));
                    })()}
                  </tbody>
                </table>
              )}
              <p className="hint">
                Distribución por canal de captación (web widget, WhatsApp, manual, etc.). Útil
                para medir TASK-0039.
              </p>
            </div>

            <div className="analytics-card">
              <h3>Top intenciones</h3>
              {(conversations?.top_intents ?? []).length === 0 ? (
                <p className="hint">Sin intenciones registradas.</p>
              ) : (
                <table className="analytics-table">
                  <thead>
                    <tr>
                      <th>Intención</th>
                      <th>Conteo</th>
                      <th>%</th>
                    </tr>
                  </thead>
                  <tbody>
                    {conversations.top_intents.map((row) => (
                      <tr key={row.intent}>
                        <td><code>{row.intent}</code></td>
                        <td>{formatNumber(row.count)}</td>
                        <td>{formatPercent(row.percentage)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="hint">
                Tiempo promedio primer respuesta del bot:{' '}
                <strong>
                  {conversations?.avg_first_bot_response_seconds
                    ? `${conversations.avg_first_bot_response_seconds.toFixed(1)} s`
                    : '-'}
                </strong>
              </p>
            </div>

            <div className="analytics-card">
              <h3>Servicios más solicitados</h3>
              {(appointments?.top_services ?? []).length === 0 ? (
                <p className="hint">Sin citas en el rango seleccionado.</p>
              ) : (
                <table className="analytics-table">
                  <thead>
                    <tr>
                      <th>Servicio</th>
                      <th>Citas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appointments.top_services.map((row) => (
                      <tr key={row.service_key}>
                        <td>{row.service_name}</td>
                        <td>{formatNumber(row.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="analytics-card">
              <h3>Distribución de citas por estado</h3>
              <div className="analytics-status-grid">
                {(appointments?.status_distribution ?? []).map((row) => (
                  <div className="status-card" key={row.status}>
                    <p className="status-label">{STATUS_LABELS[row.status] || row.status}</p>
                    <p className="status-value">{formatNumber(row.count)}</p>
                  </div>
                ))}
                {(appointments?.status_distribution ?? []).length === 0 && (
                  <p className="hint">Sin citas en el rango.</p>
                )}
              </div>
            </div>

            <div className="analytics-card">
              <h3>No-shows por día de la semana</h3>
              {(appointments?.no_shows_by_weekday ?? []).length === 0 ? (
                <p className="hint">Sin no-shows en el rango.</p>
              ) : (
                <table className="analytics-table compact">
                  <thead>
                    <tr>
                      <th>Día</th>
                      <th>No-shows</th>
                    </tr>
                  </thead>
                  <tbody>
                    {appointments.no_shows_by_weekday.map((row) => (
                      <tr key={row.weekday}>
                        <td>{WEEKDAY_LABELS[row.weekday] ?? row.weekday}</td>
                        <td>{formatNumber(row.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="analytics-card">
              <h3>Contactos</h3>
              {contacts && (
                <ul className="analytics-list">
                  <li>
                    <span>Nuevos</span>
                    <strong>{formatNumber(contacts.new_contacts)}</strong>
                  </li>
                  <li>
                    <span>Recurrentes</span>
                    <strong>{formatNumber(contacts.recurring_contacts)}</strong>
                  </li>
                  <li>
                    <span>Total</span>
                    <strong>{formatNumber(contacts.total_contacts)}</strong>
                  </li>
                  <li>
                    <span>Opt-out</span>
                    <strong>{formatPercent(contacts.opt_out_rate_pct)}</strong>
                  </li>
                </ul>
              )}
            </div>

            <div className="analytics-card">
              <h3>Top etiquetas</h3>
              {(contacts?.top_tags ?? []).length === 0 ? (
                <p className="hint">Sin etiquetas asignadas.</p>
              ) : (
                <ul className="analytics-tag-list">
                  {contacts.top_tags.map((tag) => (
                    <li key={tag.id}>
                      <span
                        className="analytics-tag-chip"
                        style={{ background: tag.color || '#dde3ee' }}
                      >
                        {tag.name}
                      </span>
                      <strong>{formatNumber(tag.count)}</strong>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="analytics-card">
              <h3>Fuente de contacto</h3>
              {(contacts?.source_distribution ?? []).length === 0 ? (
                <p className="hint">Sin contactos registrados.</p>
              ) : (
                <table className="analytics-table compact">
                  <thead>
                    <tr>
                      <th>Fuente</th>
                      <th>Contactos</th>
                    </tr>
                  </thead>
                  <tbody>
                    {contacts.source_distribution.map((row) => (
                      <tr key={row.source}>
                        <td><code>{row.source}</code></td>
                        <td>{formatNumber(row.count)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div className="analytics-card" data-testid="analytics-top-referrers">
              <h3>Top referidores</h3>
              {(referrals?.items ?? []).length === 0 ? (
                <p className="hint">
                  Aún no hay referidos registrados en el rango.
                </p>
              ) : (
                <table className="analytics-table">
                  <thead>
                    <tr>
                      <th>Embajador</th>
                      <th>Referidos</th>
                      <th>Citas</th>
                      <th>Ingreso</th>
                    </tr>
                  </thead>
                  <tbody>
                    {referrals.items.map((row) => (
                      <tr key={row.contact_id}>
                        <td>
                          <strong>{row.display_name}</strong>
                          {row.phone_e164 ? (
                            <div className="hint" style={{ fontSize: '0.75rem' }}>
                              {row.phone_e164}
                            </div>
                          ) : null}
                        </td>
                        <td>{formatNumber(row.count_referrals)}</td>
                        <td>{formatNumber(row.appointments_generated)}</td>
                        <td>{formatCurrency(row.revenue_generated)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              <p className="hint">
                Activa "¿Quién te recomendó?" en Notificaciones para que el bot
                capture el embajador durante el booking.
              </p>
            </div>
          </div>
        </>
      )}

      {tenantId && activeTab === 'overview' && !overview && !isLoading && !notice && (
        <p className="hint">Cargando métricas…</p>
      )}
    </section>
  );
}

function FunnelView({ funnel, isLoading }) {
  if (isLoading && !funnel) return <p className="hint">Cargando funnel…</p>;
  if (!funnel) return <p className="hint">Sin datos para el funnel.</p>;
  const totalSteps = funnel.total ?? [];
  const top = totalSteps[0]?.count ?? 0;
  return (
    <div className="analytics-grid">
      <div className="analytics-card">
        <h3>Funnel de conversión (total)</h3>
        {totalSteps.length === 0 ? (
          <p className="hint">Sin datos en el rango seleccionado.</p>
        ) : (
          <div className="analytics-funnel">
            {totalSteps.map((step) => {
              const widthPct = top ? Math.max((step.count / top) * 100, 4) : 0;
              return (
                <div className="analytics-funnel-row" key={step.step}>
                  <div className="analytics-funnel-label">
                    <strong>{FUNNEL_STEP_LABELS[step.step] || step.step}</strong>
                    <span>{formatNumber(step.count)}</span>
                  </div>
                  <div className="analytics-funnel-bar-track">
                    <div
                      className="analytics-funnel-bar-fill"
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                  <div className="analytics-funnel-meta">
                    <span>vs. anterior: {formatPercent(step.conversion_from_previous_pct)}</span>
                    <span>vs. top: {formatPercent(step.conversion_from_top_pct)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        <p className="hint">
          Ventana para recurrentes: {funnel.repeat_window_days ?? 90} días.
        </p>
      </div>

      <div className="analytics-card">
        <h3>Funnel por canal de captación</h3>
        {(funnel.by_channel ?? []).length === 0 ? (
          <p className="hint">Sin canales con datos.</p>
        ) : (
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Canal</th>
                {totalSteps.map((step) => (
                  <th key={step.step}>{FUNNEL_STEP_LABELS[step.step] || step.step}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {funnel.by_channel.map((row) => (
                <tr key={row.channel}>
                  <td><code>{row.channel}</code></td>
                  {row.steps.map((step) => (
                    <td key={step.step}>{formatNumber(step.count)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function CampaignsView({ campaigns, isLoading }) {
  if (isLoading && !campaigns) return <p className="hint">Cargando campañas…</p>;
  if (!campaigns) return <p className="hint">Sin datos de campañas.</p>;
  const items = campaigns.items ?? [];
  const totals = campaigns.totals ?? {};
  return (
    <>
      <div className="analytics-kpis">
        <div className="kpi-card">
          <p className="kpi-label">Campañas en rango</p>
          <p className="kpi-value">{formatNumber(totals.campaigns)}</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Citas atribuidas</p>
          <p className="kpi-value">{formatNumber(totals.appointments_attributed)}</p>
          <p className="kpi-hint">
            {formatNumber(totals.appointments_completed)} completadas
          </p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Ingreso atribuido</p>
          <p className="kpi-value">{formatCurrency(totals.revenue_attributed)}</p>
          <p className="kpi-hint">Sólo citas completadas</p>
        </div>
      </div>
      <div className="analytics-card">
        <h3>Performance por campaña</h3>
        {items.length === 0 ? (
          <p className="hint">No hay campañas con actividad en el rango.</p>
        ) : (
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Estado</th>
                <th>Recipients</th>
                <th>Response rate</th>
                <th>Citas atribuidas</th>
                <th>Ingreso atribuido</th>
                <th>Costo</th>
                <th>ROI</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.campaign_id}>
                  <td>{row.name}</td>
                  <td><code>{row.status}</code></td>
                  <td>{formatNumber(row.recipients)}</td>
                  <td>{formatPercent(row.response_rate_pct)}</td>
                  <td>
                    {formatNumber(row.appointments_attributed)}
                    {row.appointments_completed > 0 && (
                      <span className="hint">
                        {' '}({formatNumber(row.appointments_completed)} compl.)
                      </span>
                    )}
                  </td>
                  <td>{formatCurrency(row.revenue_attributed)}</td>
                  <td>
                    {row.cost_amount !== null && row.cost_amount !== undefined
                      ? `${formatNumber(row.cost_amount)} ${row.cost_currency || ''}`.trim()
                      : '-'}
                  </td>
                  <td>{row.roi_estimated !== null && row.roi_estimated !== undefined ? `${row.roi_estimated.toFixed(2)}x` : '-'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          Atribución last-touch dentro de la ventana configurable por campaña
          (default 14 días).
        </p>
      </div>
    </>
  );
}
