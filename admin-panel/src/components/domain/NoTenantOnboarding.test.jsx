import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { NoTenantOnboarding } from './NoTenantOnboarding.jsx';

describe('<NoTenantOnboarding/> (UI-016.6 refactor)', () => {
  it('muestra el heading del HTML T2 + el body explicativo', () => {
    render(<NoTenantOnboarding onCreateTenant={() => {}} />);
    expect(
      screen.getByRole('heading', {
        level: 1,
        name: 'Aún no estás asignada a un negocio',
      }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Pídele a la owner/i)).toBeInTheDocument();
  });

  it('mantiene "Crea tu tenant para empezar" como microcopy legacy', () => {
    // El router.test asserta este literal para validar que `/no-tenant` se
    // resolvió. Lo conservamos como microcopy dentro del body.
    render(<NoTenantOnboarding onCreateTenant={() => {}} />);
    expect(screen.getByText(/Crea tu tenant para empezar/i)).toBeInTheDocument();
  });

  it('dispara onCreateTenant al click en "Crear nuevo tenant"', async () => {
    const onCreateTenant = vi.fn();
    render(<NoTenantOnboarding onCreateTenant={onCreateTenant} />);
    await userEvent.click(screen.getByRole('button', { name: 'Crear nuevo tenant' }));
    expect(onCreateTenant).toHaveBeenCalledTimes(1);
  });

  it('dispara onRefresh al click en "Refrescar"', async () => {
    const onRefresh = vi.fn();
    render(<NoTenantOnboarding onCreateTenant={() => {}} onRefresh={onRefresh} />);
    await userEvent.click(screen.getByRole('button', { name: 'Refrescar' }));
    expect(onRefresh).toHaveBeenCalledTimes(1);
  });
});
