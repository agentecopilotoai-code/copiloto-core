import { Component } from 'react';

import { Button } from './Button.jsx';
import { StateScreen } from './StateScreen.jsx';
import styles from './ErrorBoundary.module.css';

/**
 * ErrorBoundary — catches render-time exceptions in its subtree and renders a
 * friendly fallback aligned to UI-016.6 (`StateScreen` con tono `danger`).
 *
 * Mantiene "Algo salió mal" como microcopy accesible para que los tests
 * existentes sigan resolviendo, mientras el heading principal usa el copy
 * del HTML `T2 _ Estados de error y bloqueos`.
 *
 * Mount one boundary per shell, wrapping only the page outlet. El primitive
 * sigue siendo dependency-free (sin Sentry/audit) — `onReport` es opcional
 * y no se llama automáticamente para no filtrar PII en el fallback.
 *
 * @typedef {Object} Props
 * @property {React.ReactNode} children
 * @property {React.ReactNode} [fallback] Optional custom fallback. When omitted
 *   the built-in `<StateScreen>` is used.
 * @property {(error: Error, info: { componentStack: string }) => void} [onReport]
 *   Called from the "Reportar al equipo" button. Receives the captured error
 *   and the React component stack.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null, info: null };
    this.handleRetry = this.handleRetry.bind(this);
    this.handleReport = this.handleReport.bind(this);
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    this.setState({ error, info });
  }

  handleRetry() {
    this.setState({ error: null, info: null });
  }

  handleReport() {
    const { onReport } = this.props;
    if (typeof onReport === 'function') {
      try {
        onReport(this.state.error, this.state.info ?? { componentStack: '' });
      } catch {
        /* swallow reporter errors to avoid masking the original crash */
      }
    }
  }

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const { fallback, onReport } = this.props;
    if (fallback) return fallback;

    // BUG-088: NO renderear `error.message` raw — leak de internals
    // (stack frames, paths internos, parámetros SQL, datos de PII en
    // mensajes de excepción mal manejadas). Mostramos un código corto
    // hash-based para que el operador pueda correlacionar contra logs/audit.
    const errorCode = error?.message
      ? `ERR-${hashErrorMessage(error.message)}`
      : null;
    return (
      <StateScreen
        tone="danger"
        role="alert"
        icon={<AlertIcon />}
        heading="Algo se rompió mientras se cargaba este módulo"
        body={
          <>
            <p>
              <strong>Algo salió mal.</strong> Capturamos el error y, si nos
              das permiso, lo enviamos a nuestro equipo. Mientras lo
              arreglamos, puedes reintentar o volver al panel.
            </p>
            {errorCode ? (
              <p className={styles.details}>
                Código de incidente: <code>{errorCode}</code>
              </p>
            ) : null}
          </>
        }
        primary={
          <Button variant="primary" onClick={this.handleRetry}>
            Reintentar
          </Button>
        }
        secondary={
          onReport ? (
            <Button variant="ghost" onClick={this.handleReport}>
              Reportar al equipo
            </Button>
          ) : null
        }
      />
    );
  }
}

// BUG-088: hash determinístico simple (FNV-1a 32-bit) → 8 hex chars.
// No es criptográfico — solo sirve para que el operador pueda buscar
// "ERR-A1B2C3D4" en logs / audit y correlacionar con el incidente.
function hashErrorMessage(message) {
  let hash = 0x811c9dc5;
  for (let i = 0; i < message.length; i += 1) {
    hash ^= message.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).toUpperCase().padStart(8, '0');
}

function AlertIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="28"
      height="28"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M5 21V4" />
      <path d="M5 5h11l-2 4 2 4H5" />
    </svg>
  );
}
