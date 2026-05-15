import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { ErrorBoundary } from './ErrorBoundary.jsx';

function Boom() {
  throw new Error('boom-test');
}

// Module-level toggle so the child renders the same on remount until the test
// flips it after the Reintentar click.
let shouldCrash = true;
function ToggleBoom() {
  if (shouldCrash) throw new Error('boom-test');
  return <p>recovered</p>;
}

describe('ErrorBoundary', () => {
  let consoleErrSpy;

  beforeEach(() => {
    // React logs caught errors to console.error; silence it for cleaner output.
    consoleErrSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    shouldCrash = true;
  });

  afterEach(() => {
    consoleErrSpy.mockRestore();
  });

  it('renders children when no error is thrown', () => {
    render(
      <ErrorBoundary>
        <p>hola</p>
      </ErrorBoundary>,
    );
    expect(screen.getByText('hola')).toBeInTheDocument();
  });

  it('renders the fallback card when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Algo salió mal')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Reintentar' })).toBeInTheDocument();
    // Without onReport, the report button is not rendered.
    expect(screen.queryByRole('button', { name: 'Reportar al equipo' })).toBeNull();
  });

  it('clears the error state when Reintentar is clicked', async () => {
    render(
      <ErrorBoundary>
        <ToggleBoom />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Algo salió mal')).toBeInTheDocument();

    // Flip the module-level switch so the child renders successfully next time.
    shouldCrash = false;
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));

    expect(screen.getByText('recovered')).toBeInTheDocument();
  });

  it('invokes onReport with the captured error when Reportar is clicked', async () => {
    const onReport = vi.fn();
    render(
      <ErrorBoundary onReport={onReport}>
        <Boom />
      </ErrorBoundary>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Reportar al equipo' }));
    expect(onReport).toHaveBeenCalledTimes(1);
    expect(onReport.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(onReport.mock.calls[0][0].message).toBe('boom-test');
  });
});
