import styles from './TimelineEntry.module.css';

/**
 * TimelineEntry — fila genérica de un timeline / lista (citas, conversaciones,
 * notas internas, eventos de consentimiento, referidos).
 *
 * No hace fetch: recibe contenido ya formateado por props.
 *
 * @param {Object} props
 * @param {React.ReactNode} [props.title]
 * @param {React.ReactNode} [props.meta] Texto secundario (fecha, autor...).
 * @param {React.ReactNode} [props.badge] Slot para un badge a la izquierda del título.
 * @param {React.ReactNode} [props.children] Cuerpo del entry.
 * @param {'li'|'div'} [props.as='li']
 */
export function TimelineEntry({ title, meta, badge, children, as: Tag = 'li' }) {
  return (
    <Tag className={styles.entry}>
      {title || badge ? (
        <div className={styles.head}>
          {badge}
          {title ? <span className={styles.title}>{title}</span> : null}
        </div>
      ) : null}
      {meta ? <span className={styles.meta}>{meta}</span> : null}
      {children ? <div className={styles.body}>{children}</div> : null}
    </Tag>
  );
}
