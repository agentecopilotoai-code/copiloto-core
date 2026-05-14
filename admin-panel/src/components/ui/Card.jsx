import styles from './Card.module.css';

/**
 * Card primitive (panel with border + soft shadow).
 *
 * @param {Object} props
 * @param {'flat'|'raised'|'alt'} [props.tone='flat'] Visual tone.
 * @param {'sm'|'md'|'lg'} [props.padding='md'] Inner padding.
 * @param {boolean} [props.interactive=false] Adds hover styles for clickable cards.
 * @param {string} [props.as] Override the root element (default: section).
 */
export function Card({
  tone = 'flat',
  padding = 'md',
  interactive = false,
  as: Tag = 'section',
  className = '',
  children,
  ...rest
}) {
  const classes = [
    styles.card,
    styles[`card--${tone}`],
    styles[`card--p-${padding}`],
    interactive ? styles['card--interactive'] : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <Tag className={classes} {...rest}>
      {children}
    </Tag>
  );
}

/**
 * Card section header (title + optional actions row).
 */
export function CardHeader({ title, subtitle, actions, className = '' }) {
  return (
    <header className={[styles.header, className].filter(Boolean).join(' ')}>
      <div className={styles.headerText}>
        {title ? <h3 className={styles.title}>{title}</h3> : null}
        {subtitle ? <p className={styles.subtitle}>{subtitle}</p> : null}
      </div>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </header>
  );
}

export function CardBody({ className = '', children }) {
  return <div className={[styles.body, className].filter(Boolean).join(' ')}>{children}</div>;
}

export function CardFooter({ className = '', children }) {
  return <footer className={[styles.footer, className].filter(Boolean).join(' ')}>{children}</footer>;
}
