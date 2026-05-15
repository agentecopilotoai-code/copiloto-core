import { Component } from 'react';

import { Button } from './Button.jsx';
import { Card, CardBody, CardFooter, CardHeader } from './Card.jsx';

/**
 * ErrorBoundary — catches render-time exceptions in its subtree and renders a
 * friendly fallback card so the rest of the shell (topbar, sidebar) stays
 * usable. Mount one boundary per shell, wrapping only the page outlet.
 *
 * The `onReport` prop is an optional hook for wiring sentry/audit later; the
 * primitive itself stays dependency-free and does NOT auto-report anything
 * (no PII is leaked in the fallback).
 *
 * @typedef {Object} Props
 * @property {React.ReactNode} children
 * @property {React.ReactNode} [fallback] Optional custom fallback. When omitted
 *   the built-in `<Card>` is used.
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

    return (
      <Card tone="raised" padding="lg" data-error-boundary="true">
        <CardHeader
          title="Algo salió mal"
          subtitle="Esta sección no pudo cargarse. Puedes reintentar o volver más tarde."
        />
        <CardBody>
          <p>
            Si el problema persiste, contacta al equipo con la hora aproximada en que ocurrió.
          </p>
        </CardBody>
        <CardFooter>
          <Button variant="ghost" onClick={this.handleRetry}>
            Reintentar
          </Button>
          {onReport ? (
            <Button variant="secondary" onClick={this.handleReport}>
              Reportar al equipo
            </Button>
          ) : null}
        </CardFooter>
      </Card>
    );
  }
}
