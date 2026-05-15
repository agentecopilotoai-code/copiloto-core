import { useEffect, useMemo, useState } from 'react';

import { AlertBanner, Card, EmptyState, PageHeader, StatusBadge } from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import { getTenantReadiness } from '../../../services/coreApi.js';
import {
  buildChecklistCsv,
  formatCheckDetails,
  groupChecksBySection,
} from './readinessSections.js';
import styles from './GoLiveReadiness.module.css';

/**
 * UI-016.1 — Go-live Readiness (Owner / Admin).
 *
 * Refactor del componente legacy al diseño entregado por el diseñador en
 * `docs/HTML DESIGN/Transversales/10b _ Inicio _ Go-live Readiness.html`:
 *
 *  - Checklist agrupado por sección (Tenant, WhatsApp, Retrieval, Operación,
 *    Cobranza). Cada sección muestra un badge `N / M`.
 *  - Counter superior `Checklist · X / Y pasados` + pill "N pendientes".
 *  - CTA "Marcar live" gated con `RequirePermission capability=
 *    "go_live_readiness.mark_live" mode="RW"` (capability nueva en `matrix.js`,
 *    exclusiva del rol owner). Botón deshabilitado mientras haya ítems
 *    pendientes; al pulsarse, no hay endpoint backend específico todavía
 *    (`UI-016.1-FU`), así que se muestra un AlertBanner explicativo.
 *  - CTA "Exportar checklist" genera un CSV client-side con el snapshot actual.
 *
 * Permission gate de lectura: `go_live_readiness.read`. El backend continúa
 * siendo la autoridad — esta vista solo es el espejo defensivo de la UI.
 *
 * @param {{ module: object, session: object, tenant: object }} props
 */
export function GoLiveReadiness({ module, session, tenant }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions({ profile, tenant });

  return (
    <RequirePermission permissions={permissions} capability="go_live_readiness.read" mode="R">
      <GoLiveReadinessContent
        module={module}
        permissions={permissions}
        session={session}
        tenant={tenant}
      />
    </RequirePermission>
  );
}

function GoLiveReadinessContent({ module, permissions, session, tenant }) {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [markLiveNotice, setMarkLiveNotice] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setReport(null);
    setError(null);
    setMarkLiveNotice(null);
    if (!tenant?.id) return undefined;
    setLoading(true);
    getTenantReadiness(session, tenant.id)
      .then((next) => {
        if (cancelled) return;
        setReport(next);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err?.message || 'No se pudo generar el checklist de go-live.');
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant?.id]);

  const grouped = useMemo(
    () => (report ? groupChecksBySection(report.checks) : []),
    [report],
  );
  const totals = useMemo(() => {
    if (!report) return { passed: 0, total: 0 };
    const total = report.checks?.length || 0;
    const passed = (report.checks || []).filter((c) => c.ready).length;
    return { passed, total };
  }, [report]);
  const pending = totals.total - totals.passed;
  const allReady = report ? Boolean(report.ready) && pending === 0 : false;
  const canMarkLive = permissions?.can?.('go_live_readiness.mark_live', 'RW') === true;

  function handleExport() {
    if (!report) return;
    const csv = buildChecklistCsv(grouped, report);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `go-live-checklist-${tenant?.slug || report.tenant_id}-${new Date()
      .toISOString()
      .slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function handleMarkLive() {
    // UI-016.1-FU: el endpoint `POST /tenants/{id}/go-live` aún no existe
    // (ver `docs/UI_BACKLOG.md`). Hasta entonces, "Marcar live" se queda en
    // frontend mostrando un AlertBanner explicativo. El botón solo se enciende
    // si TODOS los checks pasan + el owner tiene la capability `mark_live`.
    setMarkLiveNotice(
      'El endpoint de go-live se entregará en UI-016.1-FU. Mientras tanto, contacta a tu CSM para que active el flag manualmente.',
    );
  }

  return (
    <section className={styles.page}>
      <PageHeader
        eyebrow="Checklist automatizado"
        title={module?.label || 'Go-live Readiness'}
        description={
          module?.summary ||
          'La plataforma valida cada check contra el estado real del tenant. Si todo pasa, el botón "Marcar live" se activa y el tenant pasa a producción.'
        }
        actions={
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={handleExport}
              disabled={!report}
            >
              Exportar checklist
            </button>
            <RequirePermission
              permissions={permissions}
              capability="go_live_readiness.mark_live"
              mode="RW"
              hidden
            >
              <button
                type="button"
                className={styles.primaryButton}
                onClick={handleMarkLive}
                disabled={!allReady || loading}
                aria-label={
                  allReady
                    ? 'Marcar tenant como live'
                    : `Marcar live deshabilitado: ${pending} check(s) pendientes`
                }
              >
                Marcar live →
              </button>
            </RequirePermission>
          </div>
        }
      />

      {!tenant?.id ? (
        <Card padding="md">
          <EmptyState
            title="Selecciona un tenant"
            description="Elige un tenant activo para validar su checklist de go-live."
          />
        </Card>
      ) : null}

      {error ? <AlertBanner tone="danger" title={error} /> : null}

      {markLiveNotice ? (
        <AlertBanner tone="warning" title="Cierre de go-live aún manual">
          {markLiveNotice}
        </AlertBanner>
      ) : null}

      {!canMarkLive && tenant?.id ? (
        <AlertBanner tone="info" title="Solo el owner del negocio puede marcar live">
          Tu rol puede consultar el checklist pero la transición final requiere el rol Owner del tenant.
        </AlertBanner>
      ) : null}

      {report ? (
        <Card padding="md">
          <div className={styles.summaryRow}>
            <span className={styles.counterChip}>
              <span>Checklist ·</span>
              <span className={styles.counterValue}>{totals.passed}</span>
              <span className={styles.counterDivider}>/</span>
              <span className={styles.counterTotal}>{totals.total}</span>
              <span>pasados</span>
            </span>
            {pending > 0 ? (
              <StatusBadge tone="warning" variant="soft">
                {pending} pendiente{pending === 1 ? '' : 's'}
              </StatusBadge>
            ) : (
              <StatusBadge tone="success" variant="soft">Listo</StatusBadge>
            )}
          </div>
        </Card>
      ) : null}

      {loading && !report ? (
        <Card padding="md">
          <p className={styles.checkReason}>Validando checks contra el estado del tenant…</p>
        </Card>
      ) : null}

      {report && grouped.length > 0 ? (
        <div className={styles.sectionList}>
          {grouped.map((group) => (
            <SectionCard group={group} key={group.section.id} />
          ))}
        </div>
      ) : null}
    </section>
  );
}

function SectionCard({ group }) {
  const complete = group.passed === group.total;
  const badgeClass = `${styles.sectionBadge} ${complete ? styles['sectionBadge--complete'] : styles['sectionBadge--partial']}`;
  return (
    <Card padding="md" as="section" aria-labelledby={`readiness-section-${group.section.id}`}>
      <div className={styles.section}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle} id={`readiness-section-${group.section.id}`}>
            {group.section.title}
          </h2>
          <span className={badgeClass} aria-label={`${group.passed} de ${group.total} checks pasados`}>
            {group.passed} / {group.total}
          </span>
        </div>
        <ul className={styles.checkList}>
          {group.checks.map((check) => (
            <CheckRow check={check} key={check.key} />
          ))}
        </ul>
      </div>
    </Card>
  );
}

function CheckRow({ check }) {
  const detailText = formatCheckDetails(check.details);
  const iconClass = `${styles.checkIcon} ${check.ready ? styles['checkIcon--ready'] : styles['checkIcon--pending']}`;
  return (
    <li className={styles.checkRow} data-ready={check.ready ? 'true' : 'false'}>
      <span className={iconClass} aria-hidden="true">
        {check.ready ? '✓' : '!'}
      </span>
      <div className={styles.checkBody}>
        <span className={styles.checkLabel}>{check.label}</span>
        {check.reason ? <p className={styles.checkReason}>{check.reason}</p> : null}
        {detailText ? <span className={styles.checkDetails}>{detailText}</span> : null}
      </div>
    </li>
  );
}
