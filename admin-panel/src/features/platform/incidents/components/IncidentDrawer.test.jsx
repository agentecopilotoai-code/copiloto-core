import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { IncidentDrawer } from './IncidentDrawer.jsx';

describe('<IncidentDrawer/>', () => {
  it('null incident → no renderiza', () => {
    const { container } = render(<IncidentDrawer incident={null} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('pinta incident con runbook + payload entries', () => {
    render(
      <IncidentDrawer
        incident={{
          id: 'i1',
          kind: 'meta_token_expired',
          severity: 'critical',
          status: 'open',
          tenant_name: 'Acme',
          created_at: '2026-05-20T10:00:00Z',
          scheduled_for: null,
          attempts: 2,
          last_error: 'http 500',
          sent_at: null,
          runbook: 'r.md',
          payload: { foo: 'bar', nested: { a: 1 } },
        }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/Runbook/)).toBeInTheDocument();
    expect(screen.getByText('r.md')).toBeInTheDocument();
    expect(screen.getByText('foo')).toBeInTheDocument();
    expect(screen.getByText('bar')).toBeInTheDocument();
    expect(screen.getByText('nested')).toBeInTheDocument();
    expect(screen.getByText('{"a":1}')).toBeInTheDocument();
    expect(screen.getByText('http 500')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('payload vacío pinta "Sin payload adicional"', () => {
    render(
      <IncidentDrawer
        incident={{
          id: 'i1',
          kind: 'unknown',
          severity: 'low',
          status: 'open',
          tenant_name: null,
          created_at: '2026-05-20T10:00:00Z',
          scheduled_for: null,
          attempts: 0,
          last_error: null,
          sent_at: null,
          runbook: null,
          payload: {},
        }}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText(/Sin payload adicional/i)).toBeInTheDocument();
    expect(screen.getByText('Sistema (sin tenant)')).toBeInTheDocument();
    expect(screen.queryByText(/Runbook/)).toBeNull();
  });

  it('Cerrar (footer) dispara onClose', async () => {
    const onClose = vi.fn();
    render(
      <IncidentDrawer
        incident={{
          id: 'i1', kind: 'x', severity: 's', status: 'open',
          tenant_name: 'T', created_at: null, scheduled_for: null,
          attempts: 0, last_error: null, sent_at: null, runbook: null, payload: null,
        }}
        onClose={onClose}
      />,
    );
    const closeBtns = screen.getAllByRole('button', { name: 'Cerrar' });
    await userEvent.click(closeBtns.at(-1));
    expect(onClose).toHaveBeenCalled();
  });
});
