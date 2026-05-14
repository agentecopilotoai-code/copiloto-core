import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import styles from './Toast.module.css';

const ToastContext = createContext(null);

const DEFAULT_TIMEOUT = 4500;

/**
 * Toast provider — wrap the app root once and call `useToast()` to push messages.
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children
 */
export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const counter = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (toast) => {
      counter.current += 1;
      const id = `toast-${counter.current}`;
      const next = { id, tone: 'neutral', timeout: DEFAULT_TIMEOUT, ...toast };
      setToasts((prev) => [...prev, next]);
      if (next.timeout && next.timeout > 0) {
        setTimeout(() => dismiss(id), next.timeout);
      }
      return id;
    },
    [dismiss],
  );

  const value = useMemo(
    () => ({
      push,
      dismiss,
      success: (message, opts) => push({ tone: 'success', message, ...opts }),
      error: (message, opts) => push({ tone: 'danger', message, ...opts }),
      info: (message, opts) => push({ tone: 'neutral', message, ...opts }),
      warning: (message, opts) => push({ tone: 'warning', message, ...opts }),
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

/**
 * Hook to push and dismiss toasts. Must be used inside `<ToastProvider/>`.
 */
export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>');
  }
  return ctx;
}

function ToastViewport({ toasts, onDismiss }) {
  if (toasts.length === 0) return null;
  return (
    <div className={styles.viewport} role="region" aria-label="Notificaciones" aria-live="polite">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }) {
  useEffect(() => {
    // No-op; auto-dismiss is handled by the provider's setTimeout.
  }, []);
  return (
    <div className={[styles.toast, styles[`toast--${toast.tone}`]].join(' ')} role="status">
      <div className={styles.body}>
        {toast.title ? <p className={styles.title}>{toast.title}</p> : null}
        {toast.message ? <p className={styles.message}>{toast.message}</p> : null}
      </div>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        className={styles.close}
        aria-label="Cerrar notificación"
      >
        ✕
      </button>
    </div>
  );
}
