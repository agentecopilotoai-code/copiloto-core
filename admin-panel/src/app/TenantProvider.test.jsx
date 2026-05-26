import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';

vi.mock('../services/coreApi.js', () => ({
  activateSupportMode: vi.fn(),
  deactivateSupportMode: vi.fn(),
  listMyTenants: vi.fn(),
}));

vi.mock('../hooks/useTenantOptions.js', () => ({
  useTenantOptions: () => [],
}));

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../services/coreApi.js';
import {
  ACTIVE_TENANT_STORAGE_KEY,
  TenantProvider,
  pickDefaultTenant,
  useOptionalTenantContext,
  useTenantContext,
} from './TenantProvider.jsx';

const SESSION = {
  accessToken: 'tk',
  profile: { sub: 'u-1', roles: ['owner'] },
};

let lastContext;
function Probe() {
  lastContext = useTenantContext();
  return (
    <div>
      <span data-testid="count">{lastContext.tenantOptions.length}</span>
      <span data-testid="loading">{String(lastContext.tenantsLoading)}</span>
      <span data-testid="has-tenant">{String(lastContext.hasTenant)}</span>
    </div>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  lastContext = null;
  window.localStorage.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe('<TenantProvider/>', () => {
  it('hidrata tenants desde listMyTenants', async () => {
    coreApi.listMyTenants.mockResolvedValue([
      { id: 't1', slug: 'acme', display_name: 'Acme', role: 'owner', is_default: true },
      { id: 't2', slug: 'beta', display_name: 'Beta', roles: ['admin'] },
    ]);
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('2');
    });
    expect(screen.getByTestId('has-tenant').textContent).toBe('true');
  });

  it('mantiene la semilla cuando listMyTenants rejecta', async () => {
    coreApi.listMyTenants.mockRejectedValue(new Error('network'));
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });
    expect(screen.getByTestId('count').textContent).toBe('0');
  });

  it('handleTenantCreated agrega un tenant nuevo a la lista', async () => {
    coreApi.listMyTenants.mockResolvedValue([
      { id: 't1', slug: 'acme', role: 'owner' },
    ]);
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('1');
    });
    act(() => {
      lastContext.handleTenantCreated({ id: 't2', slug: 'beta' });
    });
    expect(screen.getByTestId('count').textContent).toBe('2');
  });

  it('handleTenantCreated reemplaza tenant existente con el mismo id', async () => {
    coreApi.listMyTenants.mockResolvedValue([
      { id: 't1', slug: 'acme', role: 'owner' },
    ]);
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('count').textContent).toBe('1'));
    act(() => {
      lastContext.handleTenantCreated({ id: 't1', slug: 'acme', label: 'Custom' });
    });
    expect(screen.getByTestId('count').textContent).toBe('1');
  });

  it('activateSupportMode actualiza supportModeOverride', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    coreApi.activateSupportMode.mockResolvedValue({
      expires_at: '2026-12-31T23:59:59Z',
    });
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(lastContext).not.toBeNull());
    let response;
    await act(async () => {
      response = await lastContext.activateSupportMode('t1', { justification: 'help' });
    });
    expect(coreApi.activateSupportMode).toHaveBeenCalledWith(
      SESSION,
      't1',
      { justification: 'help' },
    );
    expect(response.expires_at).toBe('2026-12-31T23:59:59Z');
    expect(lastContext.supportModeOverride.tenantId).toBe('t1');
    expect(lastContext.supportModeOverride.expiresAt).toBeInstanceOf(Date);
  });

  it('activateSupportMode retorna null y no llama al backend si no hay tenantId', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(lastContext).not.toBeNull());
    const r = await lastContext.activateSupportMode(null);
    expect(r).toBeNull();
    expect(coreApi.activateSupportMode).not.toHaveBeenCalled();
  });

  it('activateSupportMode con response sin expires_at deja null', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    coreApi.activateSupportMode.mockResolvedValue({});
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(lastContext).not.toBeNull());
    await act(async () => {
      await lastContext.activateSupportMode('t1');
    });
    expect(lastContext.supportModeOverride.expiresAt).toBeNull();
  });

  it('deactivateSupportMode limpia override aunque backend falle', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    coreApi.activateSupportMode.mockResolvedValue({ expires_at: null });
    coreApi.deactivateSupportMode.mockRejectedValue(new Error('boom'));
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(lastContext).not.toBeNull());
    await act(async () => {
      await lastContext.activateSupportMode('t1');
    });
    expect(lastContext.supportModeOverride).not.toBeNull();
    await act(async () => {
      await lastContext.deactivateSupportMode('t1');
    });
    expect(lastContext.supportModeOverride).toBeNull();
  });

  it('deactivateSupportMode happy path llama al backend', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    coreApi.deactivateSupportMode.mockResolvedValue(null);
    render(
      <TenantProvider session={SESSION}>
        <Probe />
      </TenantProvider>,
    );
    await waitFor(() => expect(lastContext).not.toBeNull());
    await act(async () => {
      await lastContext.deactivateSupportMode('t1');
    });
    expect(coreApi.deactivateSupportMode).toHaveBeenCalledWith(SESSION, 't1');
  });
});

describe('useTenantContext()', () => {
  it('throws cuando se usa fuera del provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    expect(() => render(<Probe />)).toThrow(/useTenantContext/);
    spy.mockRestore();
  });
});

describe('useOptionalTenantContext()', () => {
  function OptionalProbe() {
    const ctx = useOptionalTenantContext();
    return <span data-testid="ctx">{ctx ? 'ctx' : 'null'}</span>;
  }

  it('devuelve null sin provider', () => {
    render(<OptionalProbe />);
    expect(screen.getByTestId('ctx').textContent).toBe('null');
  });

  it('devuelve el contexto cuando está adentro', async () => {
    coreApi.listMyTenants.mockResolvedValue([]);
    render(
      <TenantProvider session={SESSION}>
        <OptionalProbe />
      </TenantProvider>,
    );
    expect(screen.getByTestId('ctx').textContent).toBe('ctx');
  });
});

describe('pickDefaultTenant()', () => {
  it('null cuando no hay tenants', () => {
    expect(pickDefaultTenant([])).toBeNull();
  });

  it('respeta localStorage cuando el id matchea', () => {
    window.localStorage.setItem(ACTIVE_TENANT_STORAGE_KEY, 't2');
    const tenants = [{ id: 't1' }, { id: 't2' }];
    expect(pickDefaultTenant(tenants).id).toBe('t2');
  });

  it('ignora localStorage cuando el id no matchea, cae a is_default', () => {
    window.localStorage.setItem(ACTIVE_TENANT_STORAGE_KEY, 'missing');
    const tenants = [{ id: 't1' }, { id: 't2', is_default: true }];
    expect(pickDefaultTenant(tenants).id).toBe('t2');
  });

  it('cae al primer tenant si no hay localStorage ni is_default', () => {
    const tenants = [{ id: 't1' }, { id: 't2' }];
    expect(pickDefaultTenant(tenants).id).toBe('t1');
  });

  it('tolera localStorage no disponible', () => {
    const original = window.localStorage;
    Object.defineProperty(window, 'localStorage', {
      get: () => { throw new Error('blocked'); },
      configurable: true,
    });
    try {
      const tenants = [{ id: 't1' }];
      expect(pickDefaultTenant(tenants).id).toBe('t1');
    } finally {
      Object.defineProperty(window, 'localStorage', {
        value: original,
        configurable: true,
      });
    }
  });
});
