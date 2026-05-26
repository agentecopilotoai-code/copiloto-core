import { useEffect, useRef } from 'react';
import styles from './Modal.module.css';

// M37 — selector de elementos focusables dentro del diálogo. Excluye
// elementos con `disabled` o `tabindex="-1"` para que el trap no se
// quede atascado en widgets escondidos del flujo.
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'area[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
  'audio[controls]',
  'video[controls]',
  '[contenteditable]:not([contenteditable="false"])',
].join(',');

function focusableElementsWithin(container) {
  if (!container) return [];
  return Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR)).filter(
    (el) => !el.hasAttribute('inert') && el.offsetParent !== null,
  );
}

/**
 * Modal — accessible dialog backed by a backdrop.
 *
 * M37 — accesibilidad: focus trap (Tab cicla dentro del diálogo,
 * Shift+Tab también), foco inicial en el primer elemento focusable
 * (o el botón cerrar como fallback), y restauración del foco al
 * elemento que abrió el modal cuando se cierra. Cumple WAI-ARIA
 * "Modal Dialog" pattern.
 *
 * @param {Object} props
 * @param {boolean} props.open
 * @param {() => void} props.onClose
 * @param {React.ReactNode} props.title
 * @param {React.ReactNode} [props.description]
 * @param {React.ReactNode} [props.footer]
 * @param {'sm'|'md'|'lg'} [props.size='md']
 * @param {boolean} [props.dismissOnBackdrop=true]
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  footer,
  size = 'md',
  dismissOnBackdrop = true,
  children,
}) {
  const dialogRef = useRef(null);
  const closeButtonRef = useRef(null);
  // Guardamos el elemento que tenía foco antes de abrir el modal para
  // restaurarlo al cerrar (UX expected del pattern Modal Dialog).
  const previouslyFocusedRef = useRef(null);
  // Ref-mirror de `onClose` para evitar que el efecto se re-arme cuando
  // el caller pasa un callback inline (cada render = nueva identidad =
  // nuevo rAF de focus que robaba el foco a inputs en plena tipeo).
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;

    previouslyFocusedRef.current = document.activeElement;

    const handler = (event) => {
      if (event.key === 'Escape') {
        onCloseRef.current?.();
        return;
      }
      if (event.key !== 'Tab') return;
      // Focus trap: Tab/Shift+Tab cicla dentro del diálogo. Si no hay
      // elementos focusables (modal solo informativo), mantenemos foco
      // en el botón cerrar.
      const focusables = focusableElementsWithin(dialogRef.current);
      if (focusables.length === 0) {
        event.preventDefault();
        closeButtonRef.current?.focus();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement;
      if (event.shiftKey) {
        if (active === first || !dialogRef.current?.contains(active)) {
          event.preventDefault();
          last.focus();
        }
      } else if (active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handler);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    // Foco inicial: primer focusable del diálogo. El efecto corre post-commit
    // así que `dialogRef.current` ya tiene los hijos pintados; no necesitamos
    // requestAnimationFrame (que introduce un gap durante el cual el usuario
    // —o el harness de tests— podría tipear y perder el primer keystroke
    // cuando el rAF roba el foco a su input).
    const initialFocusables = focusableElementsWithin(dialogRef.current);
    if (initialFocusables.length > 0) {
      initialFocusables[0].focus();
    } else {
      closeButtonRef.current?.focus();
    }

    return () => {
      document.removeEventListener('keydown', handler);
      document.body.style.overflow = prevOverflow;
      // Restaurar foco al elemento que abrió el modal (si sigue en el DOM
      // y es focusable). Si se desmontó, el foco queda en <body> — el
      // navegador lo recupera en la próxima interacción.
      const previous = previouslyFocusedRef.current;
      if (previous && typeof previous.focus === 'function' && document.contains(previous)) {
        previous.focus();
      }
    };
    // Dependemos SOLO de `open`. `onClose` se accede vía `onCloseRef.current`
    // (ver arriba) para no re-armar el efecto en cada render del padre.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  return (
    <div
      className={styles.backdrop}
      onMouseDown={(event) => {
        if (!dismissOnBackdrop) return;
        if (event.target === event.currentTarget) onClose?.();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-label={typeof title === 'string' ? title : undefined}
        className={[styles.modal, styles[`modal--${size}`]].join(' ')}
      >
        <header className={styles.head}>
          <div className={styles.headText}>
            <h2 className={styles.title}>{title}</h2>
            {description ? <p className={styles.description}>{description}</p> : null}
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Cerrar"
          >
            ✕
          </button>
        </header>
        <div className={styles.body}>{children}</div>
        {footer ? <footer className={styles.footer}>{footer}</footer> : null}
      </div>
    </div>
  );
}
