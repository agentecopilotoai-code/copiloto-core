import styles from './PageHeader.module.css';

/**
 * PageHeader — top of a feature page. Mirrors HTML design:
 * eyebrow + title + description in a row with right-aligned actions.
 *
 * @param {Object} props
 * @param {string} [props.eyebrow]
 * @param {React.ReactNode} props.title
 * @param {React.ReactNode} [props.description]
 * @param {React.ReactNode} [props.actions]
 * @param {React.ReactNode} [props.meta] Small KPIs or chips rendered below the title.
 */
export function PageHeader({ eyebrow, title, description, actions, meta, className = '' }) {
  return (
    <header className={[styles.header, className].filter(Boolean).join(' ')}>
      <div className={styles.text}>
        {eyebrow ? <span className={styles.eyebrow}>{eyebrow}</span> : null}
        <h1 className={styles.title}>{title}</h1>
        {description ? <p className={styles.description}>{description}</p> : null}
        {meta ? <div className={styles.meta}>{meta}</div> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </header>
  );
}
