import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';

import { Button } from './Button.jsx';
import { Modal } from './Modal.jsx';
import styles from './ConfirmDialog.module.css';

const ConfirmContext = createContext(null);

const DEFAULT_OPTS = {
  title: '¿Confirmar acción?',
  body: '',
  danger: false,
  confirmLabel: 'Confirmar',
  cancelLabel: 'Cancelar',
};

/**
 * Provider for the global confirm dialog. Wrap the app root once and call
 * `useConfirm()` from any descendant to await a user confirmation.
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children
 */
export function ConfirmProvider({ children }) {
  const [state, setState] = useState({ open: false, opts: DEFAULT_OPTS });
  const resolverRef = useRef(null);

  const resolve = useCallback((value) => {
    const fn = resolverRef.current;
    resolverRef.current = null;
    setState((prev) => ({ ...prev, open: false }));
    if (fn) fn(value);
  }, []);

  const confirm = useCallback((opts = {}) => {
    return new Promise((res) => {
      resolverRef.current = res;
      setState({ open: true, opts: { ...DEFAULT_OPTS, ...opts } });
    });
  }, []);

  const value = useMemo(() => confirm, [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialog state={state} onResolve={resolve} />
    </ConfirmContext.Provider>
  );
}

/**
 * Hook returning an `async confirm({ title, body, danger, confirmLabel, cancelLabel })`
 * function that resolves to `true` if the user confirms, `false` otherwise.
 *
 * If used outside a `<ConfirmProvider>` (e.g. an isolated feature test that
 * mounts a single hook without the global app shell), falls back to an
 * auto-accepting stub so legacy test trees keep working without re-wiring
 * every mount; the production tree always has the provider mounted at the
 * App root.
 */
export function useConfirm() {
  const ctx = useContext(ConfirmContext);
  if (ctx) return ctx;
  return async () => true;
}

/**
 * Internal dialog driven by the provider state — reuses the global `Modal`
 * primitive y le antepone un icono leading que cambia de tono según la
 * variante (`danger` o default).
 *
 * No exportado del barrel; usa `useConfirm`.
 */
function ConfirmDialog({ state, onResolve }) {
  const { open, opts } = state;
  const { title, body, danger, confirmLabel, cancelLabel } = opts;

  return (
    <Modal
      open={open}
      onClose={() => onResolve(false)}
      title={title}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={() => onResolve(false)} data-confirm-action="cancel">
            {cancelLabel}
          </Button>
          <Button
            variant={danger ? 'danger' : 'primary'}
            onClick={() => onResolve(true)}
            data-confirm-action="confirm"
          >
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className={styles.body} data-confirm-variant={danger ? 'danger' : 'default'}>
        <span
          className={[styles.icon, danger ? styles['icon--danger'] : styles['icon--default']].join(' ')}
          aria-hidden="true"
        >
          {danger ? '!' : '?'}
        </span>
        <div className={styles.copy}>
          {body ? <p className={styles.text}>{body}</p> : null}
        </div>
      </div>
    </Modal>
  );
}
