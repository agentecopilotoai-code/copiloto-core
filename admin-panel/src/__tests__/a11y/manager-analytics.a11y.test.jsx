import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

vi.mock('../../services/coreApi.js', () => ({
  getAnalyticsOverview: vi.fn(),
  getAnalyticsFunnel: vi.fn(),
  getAnalyticsAgents: vi.fn(),
  getAnalyticsCampaigns: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { ManagerAnalytics } from '../../features/manager/analytics/index.js';

const MANAGER_PROFILE = { sub: 'u-manager' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['manager'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Analítica', summary: 'Cómo va el negocio' };

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: MANAGER_PROFILE };
  coreApi.getAnalyticsOverview.mockResolvedValue({
    revenue: { estimated_amount: 26400 },
    appointments: { completed: 312, confirmed: 340, no_show_rate_pct: 8 },
    retention: { retention_rate_pct: 41, recurring_contacts: 120 },
    conversations: { handoff: 5 },
  });
  coreApi.getAnalyticsFunnel.mockResolvedValue({ by_channel: [] });
  coreApi.getAnalyticsAgents.mockResolvedValue({ items: [] });
  coreApi.getAnalyticsCampaigns.mockResolvedValue({ items: [] });
});

describe('a11y · Manager · Analítica', () => {
  it('a11y — Manager analytics has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <ManagerAnalytics module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(coreApi.getAnalyticsOverview).toHaveBeenCalled());

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
