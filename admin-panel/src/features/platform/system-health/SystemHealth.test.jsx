import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getSystemHealth: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import { getSystemHealth } from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { SystemHealth } from './SystemHealth.jsx';

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const HEALTH = {
  generated_at: '2026-05-14T12:00:00Z',
  snapshot: {
    messages: { inbound: 120, outbound: 95, outbound_failed: 2, outbound_error_rate: 0.021 },
    response_latency: { p50: 0.42, p95: 1.42, p99: 3.18, count: 215, avg: 0.8 },
    llm_calls: {
      total: 4820,
      success: 4810,
      success_rate: 0.998,
      by_status: { success: 4810, error: 10 },
    },
    circuit_breakers: [
      { provider: 'anthropic', state: 'closed', state_value: 0 },
      { provider: 'meta', state: 'half_open', state_value: 1 },
    ],
    workers: [
      { worker: 'event_worker', queue_depth: 12 },
      { worker: 'scheduler', queue_depth: 3 },
    ],
    outbound_dlq: { total: 3, by_error_code: { 80007: 3 } },
  },
  alerts: [
    {
      name: 'CircuitBreakerOpenSustained',
      severity: 'page',
      summary: 'Circuit breaker meta OPEN.',
      runbook_url: 'docs/runbooks/circuit-breaker-open-sustained.md',
    },
  ],
  services: [
    { key: 'api', label: 'API · FastAPI', status: 'ok', detail: 'Atendiendo requests' },
    { key: 'postgres', label: 'Postgres · primary', status: 'ok', detail: 'select 1 · 6.0ms' },
    { key: 'worker:event_worker', label: 'Worker · event_worker', status: 'ok', detail: 'queue 12' },
  ],
  note: 'Snapshot vivo del registry Prometheus in-process (TASK-0060).',
};

function setup() {
  return render(
    <MemoryRouter>
      <SystemHealth />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE },
    profile: PLATFORM_OWNER_PROFILE,
  };
  getSystemHealth.mockResolvedValue(HEALTH);
});

describe('SystemHealth', () => {
  it('renders the header, KPIs, services and breakers from the snapshot', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'System Health' }),
    ).toBeInTheDocument();

    const p95Kpi = screen.getByText('Latencia respuesta P95').closest('article');
    expect(p95Kpi.textContent).toContain('1.42 s');

    const dlqKpi = screen.getByText('Outbound DLQ acumulado').closest('article');
    expect(dlqKpi.textContent).toContain('3');

    // Services table + circuit breaker panel.
    expect(screen.getByText('API · FastAPI')).toBeInTheDocument();
    expect(screen.getByText('Postgres · primary')).toBeInTheDocument();
    expect(screen.getByText('anthropic')).toBeInTheDocument();
    expect(screen.getByText('meta')).toBeInTheDocument();
  });

  it('surfaces derived alerts from the snapshot', async () => {
    setup();
    await screen.findByRole('heading', { name: 'System Health' });

    // Node-20 + coverage instrumentation race: heading renders sync from props
    // but alerts come from the async getSystemHealth mock. findBy* waits for
    // the data to populate; getBy* would assert before the resolve fires.
    expect(await screen.findByText('CircuitBreakerOpenSustained')).toBeInTheDocument();
    expect(await screen.findByText('Circuit breaker meta OPEN.')).toBeInTheDocument();
  });

  it('renders an error state and supports retry', async () => {
    getSystemHealth.mockRejectedValueOnce(new Error('Prometheus unreachable'));
    setup();

    expect(
      await screen.findByText('No se pudo cargar System Health'),
    ).toBeInTheDocument();
    expect(screen.getByText('Prometheus unreachable')).toBeInTheDocument();

    getSystemHealth.mockResolvedValueOnce(HEALTH);
    await userEvent.click(screen.getByRole('button', { name: 'Reintentar' }));
    await screen.findByText('API · FastAPI');
  });

  it('renders AccessDenied for a non platform_owner caller', () => {
    mockTenantContext = {
      session: { profile: { sub: 'u-admin', roles: ['admin'] } },
      profile: { sub: 'u-admin', roles: ['admin'] },
    };
    setup();
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'System Health' })).toBeNull();
  });
});
