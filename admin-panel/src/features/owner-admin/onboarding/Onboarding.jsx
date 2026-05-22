import { useCallback, useEffect, useState } from 'react';

import {
  AlertBanner,
  Card,
  EmptyState,
  PageHeader,
  StatusBadge,
  Stepper,
} from '../../../components/ui/index.js';
import { RequirePermission } from '../../../permissions/index.js';
import { usePermissions } from '../../../permissions/usePermissions.js';
import { useTenantContext } from '../../../app/TenantProvider.jsx';
import {
  completeOnboardingStep,
  getTenantOnboarding,
  recordOnboardingTestMessageSent,
  verifyOnboardingStep,
} from '../../../services/coreApi.js';
import { OnboardingStep } from './components/OnboardingStep.jsx';
import { ONBOARDING_STEPS, ONBOARDING_TOTAL_STEPS, stepStatus } from './onboardingSteps.js';
import styles from './Onboarding.module.css';

const STATUS_BADGE = {
  done: { tone: 'success', label: 'Completado' },
  current: { tone: 'accent', label: 'Paso actual' },
  blocked: { tone: 'neutral', label: 'Bloqueado' },
};

const NOTICE_TONE = { success: 'success', warning: 'warning', error: 'danger', info: 'info' };

/**
 * UI-007.2 — Inicio · Onboarding self-service.
 *
 * Redesign of the legacy `OnboardingWizard` (TASK-0069): same 7-step,
 * server-verified logic, now rendered with the `Stepper` primitive, `Card`,
 * `FormField` and `AlertBanner`. The server is the authority for every step —
 * it rejects skipping with a 409, mirrored here by the per-step status.
 *
 * Visual reference: `docs/HTML DESIGN/OWNER : Admin/10 _ Inicio _ Onboarding self-service.html`.
 *
 * @param {{ session: object, tenant: object, onNavigateToModule?: (id: string) => void }} props
 */
export function Onboarding({ session, tenant, onNavigateToModule }) {
  const { profile } = useTenantContext();
  const permissions = usePermissions();
  const tenantId = tenant?.id;

  const [progress, setProgress] = useState(null);
  const [verifications, setVerifications] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [testWaId, setTestWaId] = useState('');

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    try {
      const data = await getTenantOnboarding(session, tenantId);
      setProgress(data.progress);
    } catch (error) {
      setNotice({ kind: 'error', text: error?.message || 'No se pudo cargar el onboarding.' });
    }
  }, [session, tenantId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleVerify(stepNumber) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await verifyOnboardingStep(session, tenantId, stepNumber);
      setVerifications((prev) => ({ ...prev, [stepNumber]: result }));
      setNotice(
        result.ready
          ? { kind: 'success', text: `Paso ${stepNumber} listo para completar.` }
          : { kind: 'warning', text: `Paso ${stepNumber} bloqueado: ${result.reason}` },
      );
    } catch (error) {
      setNotice({ kind: 'error', text: error?.message || `Error verificando paso ${stepNumber}.` });
    } finally {
      setBusy(false);
    }
  }

  async function handleComplete(stepNumber) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await completeOnboardingStep(session, tenantId, stepNumber);
      setProgress(result.progress);
      setNotice({ kind: 'success', text: `Paso ${stepNumber} completado.` });
    } catch (error) {
      const detail = error?.body?.detail;
      const reason = typeof detail === 'object' ? detail?.reason : detail;
      setNotice({
        kind: 'error',
        text: reason || error?.message || `No se pudo completar el paso ${stepNumber}.`,
      });
    } finally {
      setBusy(false);
    }
  }

  async function handleSendTest() {
    if (!testWaId.trim()) {
      setNotice({ kind: 'warning', text: 'Ingresa el wa_id del admin antes de enviar la prueba.' });
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      await recordOnboardingTestMessageSent(session, tenantId, testWaId.trim());
      setNotice({
        kind: 'info',
        text: `Marca registrada. Envía un mensaje desde ${testWaId.trim()} al número del tenant y verifica de nuevo.`,
      });
      refresh();
    } catch (error) {
      setNotice({ kind: 'error', text: error?.message || 'No se pudo registrar el envío de prueba.' });
    } finally {
      setBusy(false);
    }
  }

  const lastCompleted = progress?.last_completed_step ?? 0;
  const isComplete = progress?.complete === true;

  const steps = ONBOARDING_STEPS.map((step) => {
    const status = stepStatus(step.step, lastCompleted);
    const badge = STATUS_BADGE[status];
    return {
      key: step.key,
      label: step.label,
      status,
      description: step.helper,
      badge: <StatusBadge tone={badge.tone}>{badge.label}</StatusBadge>,
      children: (
        <OnboardingStep
          step={step}
          status={status}
          verification={verifications[step.step]}
          busy={busy}
          testWaId={testWaId}
          onTestWaIdChange={setTestWaId}
          onVerify={() => handleVerify(step.step)}
          onComplete={() => handleComplete(step.step)}
          onSendTest={handleSendTest}
          onGoToModule={(id) => onNavigateToModule?.(id)}
        />
      ),
    };
  });

  return (
    <RequirePermission permissions={permissions} capability="onboarding.run" mode="RW">
      <section className={styles.page}>
        <PageHeader
          eyebrow="Inicio"
          title="Onboarding self-service"
          description="Asistente guiado de 7 pasos. Cada paso se verifica antes de continuar y no se puede saltar — al terminar tu negocio queda listo para operar."
          actions={
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={busy}
              onClick={refresh}
            >
              Refrescar
            </button>
          }
          meta={
            <span className={styles.progressMeta}>
              {isComplete
                ? 'Onboarding completo'
                : `Progreso: ${lastCompleted}/${ONBOARDING_TOTAL_STEPS}`}
            </span>
          }
        />

        {notice ? (
          <AlertBanner tone={NOTICE_TONE[notice.kind] || 'info'} title={notice.text} />
        ) : null}

        {!tenantId ? (
          <Card padding="md">
            <EmptyState
              title="Selecciona un tenant"
              description="Elige un tenant activo para iniciar el wizard de onboarding de 7 pasos."
            />
          </Card>
        ) : (
          <Card padding="md">
            <Stepper steps={steps} />
          </Card>
        )}
      </section>
    </RequirePermission>
  );
}
