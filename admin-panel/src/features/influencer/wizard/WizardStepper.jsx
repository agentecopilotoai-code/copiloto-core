/**
 * UI-INFLU-014 — Stepper horizontal para el wizard "Crear personaje".
 *
 * Diseño de referencia: el PNG que envió el usuario el 2026-05-21 y
 * `docs/influencer/03a _ Crear personaje _ Paso 1 Cara.html`.
 *
 *   ✓ Cara             ── ✓ Cuerpo           ── ✓ Identidad        ── ④ Voz             ── ⑤ Plataformas
 *     Rasgos visuales      Constitución         Nombre y mundo        Tono y carácter        Dónde publica
 *
 * Estados visuales:
 *   - 'done'    → círculo verde sólido con ✓ blanco
 *   - 'current' → círculo verde sólido con número blanco
 *   - 'pending' → círculo gris claro con número gris
 *
 * Connector horizontal entre pasos: línea verde si el siguiente es done/
 * current, gris si pending.
 *
 * Acepta el mismo shape de `steps` que el <Stepper> global pero con un
 * subtítulo opcional (`description`) renderizado debajo del label.
 */
import styles from './WizardStepper.module.css';

const STATUSES = ['done', 'current', 'pending'];

export function WizardStepper({ steps, className = '' }) {
  return (
    <ol
      className={[styles.stepper, className].filter(Boolean).join(' ')}
      aria-label="Progreso del wizard"
    >
      {steps.map((step, index) => {
        const status = STATUSES.includes(step.status) ? step.status : 'pending';
        const isLast = index === steps.length - 1;
        const nextStatus = !isLast
          ? STATUSES.includes(steps[index + 1].status)
            ? steps[index + 1].status
            : 'pending'
          : null;
        const connectorActive = nextStatus === 'done' || nextStatus === 'current';
        return (
          <li
            key={step.key}
            className={[styles.step, styles[`step--${status}`]].join(' ')}
            aria-current={status === 'current' ? 'step' : undefined}
          >
            <div className={styles.head}>
              <span className={styles.marker} aria-hidden="true">
                {status === 'done' ? '✓' : index + 1}
              </span>
              <div className={styles.labelCol}>
                <span className={styles.label}>{step.label}</span>
                {step.description ? (
                  <span className={styles.description}>{step.description}</span>
                ) : null}
              </div>
            </div>
            {!isLast ? (
              <span
                className={[
                  styles.connector,
                  connectorActive ? styles['connector--active'] : '',
                ].filter(Boolean).join(' ')}
                aria-hidden="true"
              />
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
