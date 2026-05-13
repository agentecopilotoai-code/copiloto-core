import { useCallback, useEffect, useState } from 'react';

import {
  completeOnboardingStep,
  getTenantOnboarding,
  recordOnboardingTestMessageSent,
  verifyOnboardingStep,
} from '../../../services/coreApi.js';

// TASK-0069: Wizard self-service de 7 pasos con verificación paso-a-paso.
// El cliente no puede saltar al paso N+1 sin que el paso N pase el check.
const ONBOARDING_STEPS = [
  {
    step: 1,
    key: 'business_details',
    label: 'Datos del negocio',
    helper: 'Slug, razón social, vertical, país y zona horaria del tenant. Edítalo en Tenant Setup → Negocio.',
    goToModule: 'tenant-setup',
  },
  {
    step: 2,
    key: 'locale_currency',
    label: 'Timezone, locale y moneda',
    helper: 'Locale y moneda derivan del país. Configúralo en Tenant Setup → Settings y Pagos.',
    goToModule: 'tenant-setup',
  },
  {
    step: 3,
    key: 'whatsapp_channel',
    label: 'Canal WhatsApp (firma verificada contra Meta)',
    helper: 'Pega Business ID, WABA ID, Phone Number ID, access token, app secret y verify token. La firma del webhook se valida contra Meta.',
    goToModule: 'whatsapp',
  },
  {
    step: 4,
    key: 'consent_template',
    label: 'Template consent_request_v1',
    helper: 'Crea y sincroniza con Meta el template de opt-in. Solo avanza cuando Meta lo aprueba.',
    goToModule: 'whatsapp',
  },
  {
    step: 5,
    key: 'service_catalog',
    label: 'Catálogo mínimo (≥ 1 servicio)',
    helper: 'El bot no puede agendar sin saber qué se ofrece. Crea al menos un servicio activo.',
    goToModule: 'services',
  },
  {
    step: 6,
    key: 'business_hours',
    label: 'Horarios de atención',
    helper: 'Define los rangos de atención en Tenant Setup → Horarios. Al menos un día con rangos.',
    goToModule: 'tenant-setup',
  },
  {
    step: 7,
    key: 'end_to_end_test',
    label: 'Test E2E del bot',
    helper: 'Envía un mensaje de prueba al wa_id del admin y verifica que llegue un inbound de respuesta.',
    goToModule: null,
  },
];

function progressLabel(progress) {
  if (!progress) return '—';
  return `${progress.last_completed_step}/${progress.total}`;
}

function StepBadge({ step, progress }) {
  const lastCompleted = progress?.last_completed_step ?? 0;
  if (step.step <= lastCompleted) return <span className="badge badge-success">Completado</span>;
  if (step.step === lastCompleted + 1) return <span className="badge badge-primary">Paso actual</span>;
  return <span className="badge badge-muted">Bloqueado</span>;
}

export function OnboardingWizard({ session, tenant, onNavigateToModule }) {
  const tenantId = tenant?.id;
  const [progress, setProgress] = useState(null);
  const [stepsCatalog, setStepsCatalog] = useState([]);
  const [verifications, setVerifications] = useState({});
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState(null);
  const [testWaId, setTestWaId] = useState('');

  const refresh = useCallback(async () => {
    if (!tenantId) return;
    try {
      const data = await getTenantOnboarding(session, tenantId);
      setProgress(data.progress);
      setStepsCatalog(data.steps || []);
    } catch (error) {
      setNotice({ kind: 'error', text: error?.message || 'No se pudo cargar el onboarding.' });
    }
  }, [session, tenantId]);

  useEffect(() => { refresh(); }, [refresh]);

  if (!tenantId) {
    return (
      <section className="module-card">
        <h2>Onboarding self-service</h2>
        <p>Selecciona un tenant para iniciar el wizard de 7 pasos.</p>
      </section>
    );
  }

  const currentStep = (progress?.last_completed_step ?? 0) + 1;
  const isComplete = progress?.complete === true;

  async function handleVerify(stepNumber) {
    setBusy(true);
    setNotice(null);
    try {
      const result = await verifyOnboardingStep(session, tenantId, stepNumber);
      setVerifications((prev) => ({ ...prev, [stepNumber]: result }));
      if (!result.ready) {
        setNotice({ kind: 'warning', text: `Paso ${stepNumber} bloqueado: ${result.reason}` });
      } else {
        setNotice({ kind: 'success', text: `Paso ${stepNumber} listo para completar.` });
      }
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

  async function handleSendTestMessage() {
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
        text: `Marca de envío registrada. Ahora envía un mensaje desde ${testWaId.trim()} al número del tenant y vuelve a verificar.`,
      });
      refresh();
    } catch (error) {
      setNotice({ kind: 'error', text: error?.message || 'No se pudo registrar el envío de prueba.' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="module-card onboarding-wizard">
      <header className="module-card-header">
        <div>
          <h2>Onboarding self-service · 7 pasos</h2>
          <p className="muted">
            Progreso: <strong>{progressLabel(progress)}</strong> · {isComplete ? 'Onboarding completo.' : `Paso actual: ${currentStep}`}
          </p>
        </div>
        <button type="button" className="btn-secondary" disabled={busy} onClick={refresh}>
          Refrescar
        </button>
      </header>

      {notice ? (
        <div className={`notice notice-${notice.kind}`} role="status">{notice.text}</div>
      ) : null}

      <ol className="onboarding-step-list">
        {ONBOARDING_STEPS.map((step) => {
          const lastCompleted = progress?.last_completed_step ?? 0;
          const isCurrent = step.step === lastCompleted + 1;
          const isDone = step.step <= lastCompleted;
          const isBlocked = step.step > lastCompleted + 1;
          const verification = verifications[step.step];
          const meta = stepsCatalog.find((s) => s.step === step.step);
          return (
            <li key={step.step} className={`onboarding-step ${isDone ? 'done' : ''} ${isCurrent ? 'current' : ''} ${isBlocked ? 'blocked' : ''}`}>
              <div className="onboarding-step-head">
                <span className="onboarding-step-number">{step.step}</span>
                <strong>{step.label}</strong>
                <StepBadge step={step} progress={progress} />
              </div>
              <p className="muted">{step.helper}</p>
              {meta?.key && meta.key !== step.key ? (
                <small>Backend key: <code>{meta.key}</code></small>
              ) : null}

              {step.step === 7 && isCurrent ? (
                <div className="onboarding-test-block">
                  <label htmlFor="onboarding-test-wa-id">wa_id del admin (E.164 sin "+")</label>
                  <input
                    id="onboarding-test-wa-id"
                    type="text"
                    value={testWaId}
                    onChange={(event) => setTestWaId(event.target.value)}
                    placeholder="573001234567"
                    disabled={busy}
                  />
                  <button type="button" className="btn-secondary" disabled={busy} onClick={handleSendTestMessage}>
                    Marcar envío de prueba
                  </button>
                </div>
              ) : null}

              {!isBlocked ? (
                <div className="onboarding-step-actions">
                  <button type="button" className="btn-secondary" disabled={busy} onClick={() => handleVerify(step.step)}>
                    Verificar
                  </button>
                  {isCurrent ? (
                    <button
                      type="button"
                      className="btn-primary"
                      disabled={busy || !(verification?.ready)}
                      onClick={() => handleComplete(step.step)}
                    >
                      Completar paso {step.step}
                    </button>
                  ) : null}
                  {step.goToModule && onNavigateToModule ? (
                    <button type="button" className="btn-link" disabled={busy} onClick={() => onNavigateToModule(step.goToModule)}>
                      Ir al módulo →
                    </button>
                  ) : null}
                </div>
              ) : (
                <p className="muted">Bloqueado: completa el paso {lastCompleted + 1} antes de avanzar.</p>
              )}

              {verification ? (
                <p className={`onboarding-step-verification ${verification.ready ? 'ready' : 'not-ready'}`}>
                  {verification.ready ? '✓ ' : '✗ '} {verification.reason}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

export default OnboardingWizard;
