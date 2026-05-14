import styles from './Stepper.module.css';

const STATUSES = ['done', 'current', 'blocked', 'pending'];

/**
 * Stepper — vertical step list with status markers and a connector line.
 * Used by multi-step flows (onboarding wizard, tenant setup).
 *
 * Each step:
 *   { key: string, label: ReactNode, status: 'done'|'current'|'blocked'|'pending',
 *     description?: ReactNode, badge?: ReactNode, children?: ReactNode }
 *
 * `children` renders inside the step body (actions, inline forms); `badge`
 * renders on the trailing edge of the step header.
 *
 * @param {Object} props
 * @param {Array<Object>} props.steps
 */
export function Stepper({ steps, className = '' }) {
  return (
    <ol className={[styles.stepper, className].filter(Boolean).join(' ')}>
      {steps.map((step, index) => {
        const status = STATUSES.includes(step.status) ? step.status : 'pending';
        const isLast = index === steps.length - 1;
        return (
          <li key={step.key} className={[styles.step, styles[`step--${status}`]].join(' ')}>
            <div className={styles.markerCol}>
              <span className={styles.marker} aria-hidden="true">
                {status === 'done' ? '✓' : index + 1}
              </span>
              {!isLast ? <span className={styles.connector} aria-hidden="true" /> : null}
            </div>
            <div className={styles.body}>
              <div className={styles.head}>
                <span className={styles.label}>{step.label}</span>
                {step.badge ? <span className={styles.badge}>{step.badge}</span> : null}
              </div>
              {step.description ? (
                <p className={styles.description}>{step.description}</p>
              ) : null}
              {step.children ? <div className={styles.content}>{step.children}</div> : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
