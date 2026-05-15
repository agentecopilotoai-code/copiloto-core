import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { runAxe } from './axeHelper.js';

vi.mock('../../services/coreApi.js', () => ({
  listServices: vi.fn(),
  listPromotions: vi.fn(),
  getTenantSettings: vi.fn(),
  listWhatsappTemplates: vi.fn(),
  listQualificationQuestions: vi.fn(),
  createService: vi.fn(),
  updateService: vi.fn(),
  deactivateService: vi.fn(),
  reorderServices: vi.fn(),
  updateTenantSettings: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Services } from '../../features/owner-admin/services/index.js';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', label: 'Acme · acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Servicios', summary: 'Catálogo' };

const SERVICES = [
  {
    id: 's-1',
    name: 'Limpieza facial',
    category: 'Estética',
    price_amount: 120000,
    price_currency: 'COP',
    duration_minutes: 50,
    is_active: true,
  },
];

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.listServices.mockResolvedValue(SERVICES);
  coreApi.listPromotions.mockResolvedValue([]);
  coreApi.getTenantSettings.mockResolvedValue({ escalation_policy: {} });
  coreApi.listWhatsappTemplates.mockResolvedValue([]);
  coreApi.listQualificationQuestions.mockResolvedValue([]);
});

describe('a11y · Owner/Admin · Servicios', () => {
  it('a11y — Services tab has no serious/critical violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <Services module={MODULE} session={SESSION} tenant={ACME} />
      </MemoryRouter>,
    );
    await screen.findByText('Limpieza facial');

    expect(await runAxe(container)).toHaveNoViolations();
  });
});
