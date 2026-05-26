import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { IncidentsTable } from './IncidentsTable.jsx';

const baseRow = {
  id: 'i1',
  severity: 'critical',
  kind: 'meta_token_expired',
  tenant_name: 'Acme',
  status: 'open',
  created_at: '2026-05-20T10:00:00Z',
  runbook: 'meta-token-expired.md',
};

describe('<IncidentsTable/>', () => {
  it('pinta error state con Reintentar', async () => {
    const onRetry = vi.fn();
    render(
      <IncidentsTable rows={[]} loading={false} error="boom" onRetry={onRetry} onSelect={() => {}} />,
    );
    expect(screen.getByText(/No se pudo cargar Incidentes/i)).toBeInTheDocument();
    expect(screen.getByText('boom')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    expect(onRetry).toHaveBeenCalled();
  });

  it('pinta filas con runbook', () => {
    render(
      <IncidentsTable
        rows={[baseRow]}
        loading={false}
        error={null}
        onRetry={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.getByText('meta-token-expired.md')).toBeInTheDocument();
  });

  it('pinta filas sin runbook + sin tenant_name', () => {
    render(
      <IncidentsTable
        rows={[{ ...baseRow, tenant_name: null, runbook: null }]}
        loading={false}
        error={null}
        onRetry={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('Sistema (sin tenant)')).toBeInTheDocument();
    expect(screen.getByText('—')).toBeInTheDocument();
  });

  it('row click dispara onSelect', async () => {
    const onSelect = vi.fn();
    render(
      <IncidentsTable
        rows={[baseRow]}
        loading={false}
        error={null}
        onRetry={() => {}}
        onSelect={onSelect}
      />,
    );
    await userEvent.click(screen.getByText('Acme'));
    expect(onSelect).toHaveBeenCalledWith(baseRow);
  });

  it('handlea severity/status desconocidos con tone neutral', () => {
    render(
      <IncidentsTable
        rows={[{ ...baseRow, severity: 'unknown', status: 'weird', kind: 'mystery' }]}
        loading={false}
        error={null}
        onRetry={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('unknown')).toBeInTheDocument();
    expect(screen.getByText('weird')).toBeInTheDocument();
    expect(screen.getByText('mystery')).toBeInTheDocument();
  });
});
