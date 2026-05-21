import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

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
import { listTenantModules, updateTenantModule } from '../../../../services/coreApi.js';
import { TenantModulesPanel } from './TenantModulesPanel.jsx';
import { TENANT_MODULES_CATALOG } from '../hooks/useTenantModules.js';

const TENANT = {
  id: 'tenant-1',
  slug: 'clinica-norte',
  display_name: 'Clínica Estética Norte',
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
  // Por default: el tenant solo tiene `influencer` activo y `analytics` inactivo
  // (el resto del catálogo nunca se activó, no aparecen en el endpoint).
  listTenantModules.mockResolvedValue({
    items: [
      {
        tenant_id: 'tenant-1',
        tenant_slug: 'clinica-norte',
        tenant_name: 'Clínica Norte',
        module: 'influencer',
        enabled: true,
        plan: null,
        activated_at: '2026-04-15T12:00:00Z',
        activated_by: 'u-platform',
        notes: null,
      },
      {
        tenant_id: 'tenant-1',
        tenant_slug: 'clinica-norte',
        tenant_name: 'Clínica Norte',
        module: 'analytics',
        enabled: false,
        plan: null,
        activated_at: '2026-03-01T10:00:00Z',
        activated_by: 'u-platform',
        notes: null,
      },
    ],
  });
});

describe('TenantModulesPanel', () => {
  it('renderiza todos los módulos del catálogo con estado del backend', async () => {
    render(<TenantModulesPanel tenant={TENANT} />);

    expect(await screen.findByText('Módulos contratados')).toBeInTheDocument();

    // Todos los módulos del catálogo deben aparecer (no solo los del backend).
    for (const cat of TENANT_MODULES_CATALOG) {
      expect(screen.getByText(cat.label)).toBeInTheDocument();
    }

    // influencer está ON, analytics está OFF, el resto OFF (nunca activado).
    const switches = screen.getAllByRole('switch');
    expect(switches).toHaveLength(TENANT_MODULES_CATALOG.length);

    const influencerSwitch = screen.getByRole('switch', { name: /Desactivar Influencer Studio/i });
    expect(influencerSwitch).toBeChecked();

    const analyticsSwitch = screen.getByRole('switch', { name: /Activar Analítica de negocio/i });
    expect(analyticsSwitch).not.toBeChecked();
  });

  it('llama updateTenantModule cuando platform_owner activa un módulo', async () => {
    updateTenantModule.mockResolvedValue({
      tenant_id: 'tenant-1',
      tenant_slug: 'clinica-norte',
      tenant_name: 'Clínica Norte',
      module: 'chatbot',
      enabled: true,
      plan: null,
      activated_at: '2026-05-20T20:00:00Z',
      activated_by: 'u-platform',
      notes: null,
    });

    render(<TenantModulesPanel tenant={TENANT} />);
    await screen.findByText('Módulos contratados');

    const chatbotSwitch = screen.getByRole('switch', { name: /Activar Chatbot conversacional/i });
    await userEvent.click(chatbotSwitch);

    await waitFor(() => {
      expect(updateTenantModule).toHaveBeenCalledWith(
        expect.anything(),
        'tenant-1',
        'chatbot',
        expect.objectContaining({ enabled: true, plan: null, notes: null }),
      );
    });
  });

  it('muestra el error del backend si la mutación falla (ej. MFA expirado)', async () => {
    updateTenantModule.mockRejectedValue(new Error('mfa required'));

    render(<TenantModulesPanel tenant={TENANT} />);
    await screen.findByText('Módulos contratados');

    const paymentsSwitch = screen.getByRole('switch', { name: /Activar Pagos/i });
    await userEvent.click(paymentsSwitch);

    expect(await screen.findByRole('alert')).toHaveTextContent('mfa required');
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

  it('expone el módulo gestion_documental en el catálogo (decisión D1=C)', () => {
    const codes = TENANT_MODULES_CATALOG.map((cat) => cat.code);
    expect(codes).toContain('gestion_documental');
    expect(codes).toContain('influencer');
    expect(codes).toContain('chatbot');
    expect(codes).toContain('widget_web');
    expect(codes).toContain('campaigns');
    expect(codes).toContain('analytics');
    expect(codes).toContain('payments');
    expect(codes).toHaveLength(7);
  });
});
