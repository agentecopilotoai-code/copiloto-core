import styles from './StateScreen.module.css';

/**
 * StateScreen — UI-016.6 primitive that enforces a consistent layout for the
 * five application-state screens defined in
 * `docs/HTML DESIGN/Transversales/T2 _ Estados de error y bloqueos.html`:
 * `/no-tenant`, `AccessDenied`, `MfaRequiredBlocker`, the 404 catch-all and
 * the `ErrorBoundary` fallback.
 *
 * The mockup mandates: minimal icon, heading, body, one primary action plus
 * one optional secondary action, centered on a calm background card. Tone
 * controls the soft accent strip (neutral / warning / danger).
 *
 * Callers pass `primary` and `secondary` as React nodes so each screen owns
 * its own nav semantics (`<Button>`, `<a>`, `<form>` for MFA logout, etc.).
 *
 * @param {Object} props
 * @param {React.ReactNode} [props.icon] Minimal illustration (SVG / emoji).
 * @param {React.ReactNode} props.heading Required H1 copy.
 * @param {React.ReactNode} [props.body] Paragraph(s) explaining the state.
 * @param {React.ReactNode} [props.primary] Primary CTA node.
 * @param {React.ReactNode} [props.secondary] Secondary CTA node.
 * @param {'neutral'|'warning'|'danger'} [props.tone='neutral'] Visual accent.
 * @param {'status'|'alert'|'alertdialog'} [props.role='status'] ARIA role.
 *   `MfaRequiredBlocker` uses `alertdialog` (non-dismissable gate); the rest
 *   default to `status` (announced politely without trapping focus).
 * @param {boolean} [props.modal=false] When true, sets `aria-modal` for the
 *   MFA blocker overlay variant.
 * @param {string} [props.className]
 */
export function StateScreen({
  icon,
  heading,
  body,
  primary,
  secondary,
  tone = 'neutral',
  role = 'status',
  modal = false,
  className = '',
}) {
  const classes = [
    styles.screen,
    styles[`screen--${tone}`],
    modal ? styles['screen--modal'] : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <section
      className={classes}
      role={role}
      aria-live={role === 'status' ? 'polite' : undefined}
      aria-modal={modal ? 'true' : undefined}
    >
      <div className={styles.card}>
        {icon ? (
          <div className={styles.icon} aria-hidden="true">
            {icon}
          </div>
        ) : null}
        <h1 className={styles.heading}>{heading}</h1>
        {body ? <div className={styles.body}>{body}</div> : null}
        {primary || secondary ? (
          <div className={styles.actions}>
            {secondary}
            {primary}
          </div>
        ) : null}
      </div>
    </section>
  );
}
