import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  getTenantOnboarding: vi.fn(),
  verifyOnboardingStep: vi.fn(),
  completeOnboardingStep: vi.fn(),
  recordOnboardingTestMessageSent: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import {
  getTenantOnboarding,
  verifyOnboardingStep,
} from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { Onboarding } from './Onboarding.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <Onboarding session={SESSION} tenant={tenant} onNavigateToModule={vi.fn()} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  getTenantOnboarding.mockResolvedValue({
    progress: { last_completed_step: 3, total: 7, complete: false },
  });
  verifyOnboardingStep.mockResolvedValue({ ready: false, reason: 'falta el catálogo' });
});

describe('Onboarding', () => {
  it('renders the wizard header, progress and the 7 stepper steps', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Onboarding self-service' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Progreso: 3/7')).toBeInTheDocument();
    // a done step, the current step and a blocked step are all rendered
    expect(screen.getByText('Datos del negocio')).toBeInTheDocument();
    expect(screen.getByText('Catálogo mínimo (≥ 1 servicio)')).toBeInTheDocument();
    expect(screen.getByText('Test E2E del bot')).toBeInTheDocument();
  });

  it('verifies a step through the server', async () => {
    setup();
    await screen.findByRole('heading', { name: 'Onboarding self-service' });

    // step 4 is the current step (3 completed) — its Verificar button is live.
    const verifyButtons = screen.getAllByRole('button', { name: 'Verificar' });
    await userEvent.click(verifyButtons[verifyButtons.length - 1]);

    await waitFor(() => {
      expect(verifyOnboardingStep).toHaveBeenCalledWith(SESSION, 'tenant-acme', 4);
    });
    // the notice banner echoes the server reason for the current step (4)
    expect(
      await screen.findByText('Paso 4 bloqueado: falta el catálogo'),
    ).toBeInTheDocument();
  });

  it('renders AccessDenied for a role without onboarding.run', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['manager'] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Onboarding self-service' }),
    ).toBeNull();
  });
});
