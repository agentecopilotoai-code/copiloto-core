import styles from './TagPill.module.css';

/**
 * TagPill — chip de etiqueta de contacto, con color provisto por la API.
 *
 * El color es dato dinámico del backend (`tag.color`), no un token de diseño;
 * se inyecta vía la custom property `--tag-color` y cae a `var(--accent)`.
 *
 * @param {Object} props
 * @param {{ id?: string, name: string, color?: string }} props.tag
 * @param {() => void} [props.onRemove] Si se pasa, muestra el botón de quitar.
 * @param {boolean} [props.disabled=false] Deshabilita el botón de quitar.
 * @param {'sm'|'md'} [props.size='md']
 */
export function TagPill({ tag, onRemove, disabled = false, size = 'md' }) {
  if (!tag) return null;
  const safeSize = size === 'sm' ? 'sm' : 'md';
  const style = tag.color ? { '--tag-color': tag.color } : undefined;
  return (
    <span className={[styles.pill, styles[`pill--${safeSize}`]].join(' ')} style={style}>
      <span className={styles.label}>{tag.name}</span>
      {onRemove ? (
        <button
          type="button"
          className={styles.remove}
          aria-label={`Quitar etiqueta ${tag.name}`}
          onClick={onRemove}
          disabled={disabled}
        >
          ×
        </button>
      ) : null}
    </span>
  );
}
