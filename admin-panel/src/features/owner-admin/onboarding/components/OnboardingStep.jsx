import { FormField } from '../../../../components/ui/index.js';
import styles from '../Onboarding.module.css';

/**
 * Per-step body for the onboarding wizard: the verify / complete / "go to
 * module" actions, the step-7 test-message form, and the inline verification
 * result. The wizard logic lives in the parent view — this component is a dumb
 * renderer driven by props.
 *
 * @param {{
 *   step: object,
 *   status: 'done'|'current'|'blocked',
 *   verification: object|undefined,
 *   busy: boolean,
 *   testWaId: string,
 *   onTestWaIdChange: (value: string) => void,
 *   onVerify: () => void,
 *   onComplete: () => void,
 *   onSendTest: () => void,
 *   onGoToModule: (moduleId: string) => void,
 * }} props
 */
export function OnboardingStep({
  step,
  status,
  verification,
  busy,
  testWaId,
  onTestWaIdChange,
  onVerify,
  onComplete,
  onSendTest,
  onGoToModule,
}) {
  const isCurrent = status === 'current';
  const isBlocked = status === 'blocked';

  if (isBlocked) {
    return (
      <p className={styles.blockedNote}>
        Bloqueado: completa los pasos previos antes de avanzar.
      </p>
    );
  }

  return (
    <div className={styles.stepBody}>
      {step.step === 7 && isCurrent ? (
        <div className={styles.testBlock}>
          <FormField
            label="wa_id del admin (E.164 sin +)"
            hint="Manda un mensaje desde ese número al WhatsApp del tenant y vuelve a verificar."
          >
            <input
              type="text"
              value={testWaId}
              onChange={(event) => onTestWaIdChange(event.target.value)}
              placeholder="573001234567"
              disabled={busy}
            />
          </FormField>
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={busy}
            onClick={onSendTest}
          >
            Marcar envío de prueba
          </button>
        </div>
      ) : null}

      <div className={styles.stepActions}>
        <button
          type="button"
          className={styles.secondaryButton}
          disabled={busy}
          onClick={onVerify}
        >
          Verificar
        </button>
        {isCurrent ? (
          <button
            type="button"
            className={styles.primaryButton}
            disabled={busy || !verification?.ready}
            onClick={onComplete}
          >
            Completar paso {step.step}
          </button>
        ) : null}
        {step.goToModule ? (
          <button
            type="button"
            className={styles.linkButton}
            disabled={busy}
            onClick={() => onGoToModule(step.goToModule)}
          >
            Ir al módulo →
          </button>
        ) : null}
      </div>

      {verification ? (
        <p
          className={
            verification.ready ? styles.verificationOk : styles.verificationFail
          }
        >
          {verification.ready ? '✓ ' : '✗ '}
          {verification.reason}
        </p>
      ) : null}
    </div>
  );
}
