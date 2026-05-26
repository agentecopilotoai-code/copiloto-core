import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../services/coreApi.js', () => ({
  listTenantModules: vi.fn(),
  updateTenantModule: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../../../../services/coreApi.js';
import { TenantModulesPanel } from './TenantModulesPanel.jsx';
import { TENANT_MODULES_CATALOG } from '../hooks/useTenantModules.js';

const TENANT = { id: 't1', slug: 'acme', display_name: 'Acme' };
const PLATFORM_OWNER = {
  sub: 'po', roles: ['platform_owner'], support_mode: true,
};
const OWNER = { sub: 'o', roles: ['owner'] };

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = {
    session: { profile: PLATFORM_OWNER, accessToken: 'tk' },
    profile: PLATFORM_OWNER,
  };
  coreApi.listTenantModules.mockResolvedValue({ items: [] });
});

describe('<TenantModulesPanel/>', () => {
  it('platform_owner ve el header con el catálogo del core (vacío)', async () => {
    render(<TenantModulesPanel tenant={TENANT} />);
    expect(await screen.findByText('Módulos contratados')).toBeInTheDocument();
    expect(screen.queryAllByRole('switch')).toHaveLength(TENANT_MODULES_CATALOG.length);
  });

  it('no renderiza para owner del tenant (defensa en profundidad)', () => {
    mockTenantContext = {
      session: { profile: OWNER, accessToken: 'tk' },
      profile: OWNER,
    };
    const { container } = render(<TenantModulesPanel tenant={TENANT} />);
    expect(container).toBeEmptyDOMElement();
    expect(coreApi.listTenantModules).not.toHaveBeenCalled();
  });

  it('pinta error cuando la query del backend falla', async () => {
    coreApi.listTenantModules.mockRejectedValue(new Error('rls bloqueado'));
    // Inyectamos una entry para forzar el render de filas (de lo contrario
    // el panel queda con `rows=[]` y nunca pinta el bloque que llama al
    // backend con error).
    TENANT_MODULES_CATALOG.push({
      code: 'demo',
      label: 'Demo Module',
      description: 'Demo.',
    });
    try {
      render(<TenantModulesPanel tenant={TENANT} />);
      expect(await screen.findByRole('alert')).toHaveTextContent('rls bloqueado');
    } finally {
      TENANT_MODULES_CATALOG.length = 0;
    }
  });

  it('ejercita switch ON/OFF + last-change status cuando hay catálogo', async () => {
    TENANT_MODULES_CATALOG.push({
      code: 'demo',
      label: 'Demo Module',
      description: 'Ejemplo en test.',
    });
    coreApi.listTenantModules.mockResolvedValue({
      items: [
        {
          tenant_id: 't1',
          module: 'demo',
          enabled: true,
          plan: null,
          activated_at: '2026-05-20T10:00:00Z',
          activated_by: 'po',
          notes: null,
        },
      ],
    });
    coreApi.updateTenantModule.mockResolvedValue({
      tenant_id: 't1', module: 'demo', enabled: false,
      plan: null, activated_at: '2026-05-21T10:00:00Z', activated_by: 'po', notes: null,
    });
    try {
      render(<TenantModulesPanel tenant={TENANT} />);
      const switchEl = await screen.findByRole('switch', { name: /Desactivar Demo Module/i });
      expect(switchEl).toBeChecked();
      await userEvent.click(switchEl);
      await waitFor(() => {
        expect(coreApi.updateTenantModule).toHaveBeenCalledWith(
          mockTenantContext.session,
          't1',
          'demo',
          expect.objectContaining({ enabled: false }),
        );
      });
      expect(await screen.findByRole('status')).toHaveTextContent('demo');
    } finally {
      TENANT_MODULES_CATALOG.length = 0;
    }
  });

  it('swallowea el error del toggle silenciosamente (lo expone el hook)', async () => {
    TENANT_MODULES_CATALOG.push({
      code: 'demo',
      label: 'Demo Module',
      description: 'Demo.',
    });
    coreApi.listTenantModules.mockResolvedValue({
      items: [{
        tenant_id: 't1', module: 'demo', enabled: false,
        plan: null, activated_at: null, activated_by: null, notes: null,
      }],
    });
    coreApi.updateTenantModule.mockRejectedValue(new Error('mfa required'));
    try {
      render(<TenantModulesPanel tenant={TENANT} />);
      const switchEl = await screen.findByRole('switch', { name: /Activar Demo Module/i });
      await userEvent.click(switchEl);
      await waitFor(() => {
        expect(screen.getByRole('alert')).toHaveTextContent('mfa required');
      });
    } finally {
      TENANT_MODULES_CATALOG.length = 0;
    }
  });
});
