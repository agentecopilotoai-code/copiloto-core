import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import styles from './Toast.module.css';

const ToastContext = createContext(null);

// Auto-close durations per UI-016.5 spec.
//   success / info -> 4s  · warn / error -> 8s.
const TIMEOUT_BY_TONE = {
  success: 4000,
  info: 4000,
  warn: 8000,
  error: 8000,
  neutral: 4000,
};

// Stack max per UI-016.5 spec: hasta 5 toasts visibles; resto en cola.
const MAX_VISIBLE = 5;

// Backwards-compatible aliases. `warning` and `danger` map to `warn` and
// `error` so existing call sites keep working without touch-ups.
const TONE_ALIASES = {
  warning: 'warn',
  danger: 'error',
};

const ICON_BY_TONE = {
  success: '✓',
  info: 'i',
  warn: '!',
  error: '×',
  neutral: '·',
};

function normalizeTone(tone) {
  if (!tone) return 'neutral';
  return TONE_ALIASES[tone] || tone;
}

function timeoutFor(tone, explicit) {
  if (explicit !== undefined) return explicit;
  return TIMEOUT_BY_TONE[tone] ?? TIMEOUT_BY_TONE.neutral;
}

/**
 * Toast provider — wrap the app root once and call `useToast()` to push messages.
 *
 * Toasts apilan en la esquina inferior derecha. Hasta 5 visibles, los
 * excedentes esperan en una cola FIFO y aparecen cuando se cierra alguno
 * de los visibles. Auto-cierre 4s (success/info) o 8s (warn/error).
 *
 * @param {Object} props
 * @param {React.ReactNode} props.children
 */
export function ToastProvider({ children }) {
  const [visible, setVisible] = useState([]);
  const queueRef = useRef([]);
  const counter = useRef(0);
  const timersRef = useRef(new Map());

  const clearTimer = useCallback((id) => {
    const handle = timersRef.current.get(id);
    if (handle) {
      clearTimeout(handle);
      timersRef.current.delete(id);
    }
  }, []);

  const dismiss = useCallback(
    (id) => {
      clearTimer(id);
      // Drain the queue inside the same state update so the promotion
      // commits together with the removal — robust under fake timers
      // (no reliance on microtasks).
      setVisible((prev) => {
        const kept = prev.filter((t) => t.id !== id);
        while (kept.length < MAX_VISIBLE && queueRef.current.length > 0) {
          kept.push(queueRef.current.shift());
        }
        return kept;
      });
    },
    [clearTimer],
  );

  const scheduleAutoClose = useCallback(
    (toast) => {
      if (!toast.timeout || toast.timeout <= 0) return;
      const handle = setTimeout(() => dismiss(toast.id), toast.timeout);
      timersRef.current.set(toast.id, handle);
    },
    [dismiss],
  );

  const push = useCallback(
    (toast) => {
      counter.current += 1;
      const id = `toast-${counter.current}`;
      const tone = normalizeTone(toast?.tone);
      const next = {
        id,
        tone,
        title: toast?.title || '',
        message: toast?.message || '',
        action: toast?.action || null,
        timeout: timeoutFor(tone, toast?.timeout),
      };
      setVisible((prev) => {
        if (prev.length < MAX_VISIBLE) {
          scheduleAutoClose(next);
          return [...prev, next];
        }
        // Queued: timer starts when promoted to visible.
        queueRef.current.push(next);
        return prev;
      });
      return id;
    },
    [scheduleAutoClose],
  );

  // When a queued toast gets promoted to visible (via setVisible inside
  // promoteFromQueue), start its auto-close timer here. We track which
  // visible ids already have a timer attached via timersRef.
  useEffect(() => {
    visible.forEach((toast) => {
      if (toast.timeout > 0 && !timersRef.current.has(toast.id)) {
        scheduleAutoClose(toast);
      }
    });
  }, [visible, scheduleAutoClose]);

  // Cleanup timers on unmount.
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((h) => clearTimeout(h));
      timers.clear();
    };
  }, []);

  const value = useMemo(
    () => ({
      push,
      dismiss,
      success: (message, opts) => push({ ...opts, tone: 'success', message }),
      error: (message, opts) => push({ ...opts, tone: 'error', message }),
      info: (message, opts) => push({ ...opts, tone: 'info', message }),
      warning: (message, opts) => push({ ...opts, tone: 'warn', message }),
    }),
    [push, dismiss],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport toasts={visible} onDismiss={dismiss} />
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
    <div className={styles.viewport} aria-label="Notificaciones">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastItem({ toast, onDismiss }) {
  // warn / error → role="alert" + assertive; success / info → role="status".
  const isUrgent = toast.tone === 'warn' || toast.tone === 'error';
  const role = isUrgent ? 'alert' : 'status';
  const live = isUrgent ? 'assertive' : 'polite';
  return (
    <div
      className={[styles.toast, styles[`toast--${toast.tone}`]].join(' ')}
      role={role}
      aria-live={live}
      data-tone={toast.tone}
    >
      <span className={styles.icon} aria-hidden="true">
        {ICON_BY_TONE[toast.tone] ?? ICON_BY_TONE.neutral}
      </span>
      <div className={styles.body}>
        {toast.title ? <p className={styles.title}>{toast.title}</p> : null}
        {toast.message ? <p className={styles.message}>{toast.message}</p> : null}
        {toast.action ? (
          <button
            type="button"
            className={styles.action}
            onClick={() => {
              toast.action.onClick?.();
              if (toast.action.dismissOnClick !== false) onDismiss(toast.id);
            }}
          >
            {toast.action.label}
          </button>
        ) : null}
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
