import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock coreApi BEFORE importing the component so the dynamic graph picks the mocks.
vi.mock('../../../../services/coreApi.js', () => ({
  listTenantModules: vi.fn(),
  updateTenantModule: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { listTenantModules } from '../../../../services/coreApi.js';
import { TenantModulesPanel } from './TenantModulesPanel.jsx';
import { TENANT_MODULES_CATALOG } from '../hooks/useTenantModules.js';

const TENANT = {
  id: 'tenant-1',
  slug: 'acme',
  display_name: 'Acme',
};

const PLATFORM_OWNER_PROFILE = {
  sub: 'u-platform',
  roles: ['platform_owner'],
  support_mode: true,
};

const OWNER_PROFILE = {
  sub: 'u-owner',
  roles: ['owner'],
};

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER_PROFILE, accessToken: 'token-x' },
    profile: PLATFORM_OWNER_PROFILE,
  };
  listTenantModules.mockResolvedValue({ items: [] });
});

describe('TenantModulesPanel', () => {
  it('platform_owner ve el header del panel y el catálogo vacío del core', async () => {
    render(<TenantModulesPanel tenant={TENANT} />);
    expect(await screen.findByText('Módulos contratados')).toBeInTheDocument();
    const switches = screen.queryAllByRole('switch');
    expect(switches).toHaveLength(TENANT_MODULES_CATALOG.length);
  });

  it('no renderiza para usuarios con rol owner (defensa en profundidad)', () => {
    mockTenantContext = {
      session: { profile: OWNER_PROFILE, accessToken: 'token-x' },
      profile: OWNER_PROFILE,
    };
    const { container } = render(<TenantModulesPanel tenant={TENANT} />);
    expect(container).toBeEmptyDOMElement();
    expect(listTenantModules).not.toHaveBeenCalled();
  });

  it('catálogo del core arranca vacío (módulos opt-in se registran cuando se instalan)', () => {
    expect(TENANT_MODULES_CATALOG).toEqual([]);
  });
});
