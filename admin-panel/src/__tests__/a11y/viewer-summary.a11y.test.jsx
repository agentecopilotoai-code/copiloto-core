import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

vi.mock('../../services/coreApi.js', () => ({
  getAnalyticsOverview: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { ViewerSummary } from '../../features/viewer/summary/index.js';

const VIEWER_PROFILE = { sub: 'u-viewer' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Resumen del negocio', summary: 'Lectura' };

const CURRENT_OVERVIEW = {
  appointments: { confirmed: 42, created: 60, completed: 38, no_shows: 3, no_show_rate_pct: 5 },
  conversations: { open: 12, handoff: 2 },
  messages: { inbound: 410, outbound: 380 },
  revenue: { estimated_amount: 26400 },
};
const PREVIOUS_OVERVIEW = {
  appointments: { confirmed: 35, created: 52, completed: 30, no_shows: 5, no_show_rate_pct: 9 },
  conversations: { open: 14, handoff: 4 },
  messages: { inbound: 380, outbound: 350 },
  revenue: { estimated_amount: 22100 },
};

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: VIEWER_PROFILE };
  coreApi.getAnalyticsOverview
    .mockResolvedValueOnce(CURRENT_OVERVIEW)
    .mockResolvedValueOnce(PREVIOUS_OVERVIEW);
});

describe('a11y · Viewer · Resumen', () => {
  it('a11y — Viewer summary has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <ViewerSummary module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    await waitFor(() => expect(coreApi.getAnalyticsOverview).toHaveBeenCalledTimes(2));

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
