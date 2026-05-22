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
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import {
  getTenantOnboarding,
  verifyOnboardingStep,
  completeOnboardingStep,
  recordOnboardingTestMessageSent,
} from '../../../services/coreApi.js';
// eslint-disable-next-line no-unused-vars -- vitest hoists vi.mock
import { Onboarding } from './Onboarding.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };

function setup({ tenant = ACME } = {}) {
    mockTenantContext.activeTenant = tenant;
  return render(
    <MemoryRouter>
      <Onboarding session={SESSION} tenant={tenant} onNavigateToModule={vi.fn()} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE, activeTenant: ACME };
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
    // Wait for the getTenantOnboarding mock to resolve before reading the
    // Verificar buttons — on slow runners (CI Node 20) the heading renders
    // before progress=null becomes {last_completed_step:3}, which would leave
    // only step 1's button visible and make the test click the wrong step.
    await screen.findByText('Progreso: 3/7');

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

  it('renders the empty-tenant card and "Onboarding completo" meta path', async () => {
    setup({ tenant: { id: undefined, slug: 'x', roles: ['owner'] } });
    expect(screen.getByText(/Selecciona un tenant/i)).toBeInTheDocument();
  });

  it('shows "Onboarding completo" in the header meta when progress.complete is true', async () => {
    getTenantOnboarding.mockResolvedValueOnce({
      progress: { last_completed_step: 7, total: 7, complete: true },
    });
    setup();
    expect(await screen.findByText('Onboarding completo')).toBeInTheDocument();
  });

  it('surfaces an error notice when getTenantOnboarding fails', async () => {
    getTenantOnboarding.mockRejectedValueOnce(new Error('fail-load'));
    setup();
    expect(await screen.findByText('fail-load')).toBeInTheDocument();
  });

  it('surfaces a success notice and updates progress when completeOnboardingStep succeeds', async () => {
    completeOnboardingStep.mockResolvedValueOnce({
      progress: { last_completed_step: 4, total: 7, complete: false },
    });
    // Force the current step's verify result into a ready=true state so the
    // OnboardingStep exposes a "Completar" button. We make verifyOnboardingStep
    // return ready=true for the current step.
    verifyOnboardingStep.mockResolvedValueOnce({ ready: true });
    setup();
    await screen.findByText('Progreso: 3/7');

    const verifyButtons = screen.getAllByRole('button', { name: 'Verificar' });
    await userEvent.click(verifyButtons[verifyButtons.length - 1]);
    await screen.findByText('Paso 4 listo para completar.');

    const completeBtn = await screen.findByRole('button', { name: /Completar paso 4/ });
    await userEvent.click(completeBtn);

    await waitFor(() => {
      expect(completeOnboardingStep).toHaveBeenCalledWith(SESSION, 'tenant-acme', 4);
    });
    expect(await screen.findByText('Paso 4 completado.')).toBeInTheDocument();
  });

  it('surfaces an error notice when completeOnboardingStep throws with a detail.reason', async () => {
    const err = new Error('boom');
    err.body = { detail: { reason: 'falta config' } };
    completeOnboardingStep.mockRejectedValueOnce(err);
    verifyOnboardingStep.mockResolvedValueOnce({ ready: true });
    setup();
    await screen.findByText('Progreso: 3/7');

    const verifyButtons = screen.getAllByRole('button', { name: 'Verificar' });
    await userEvent.click(verifyButtons[verifyButtons.length - 1]);
    await screen.findByText('Paso 4 listo para completar.');

    const completeBtn = await screen.findByRole('button', { name: /Completar paso 4/ });
    await userEvent.click(completeBtn);

    expect(await screen.findByText('falta config')).toBeInTheDocument();
  });

  it('refresh button retriggers getTenantOnboarding', async () => {
    setup();
    await screen.findByText('Progreso: 3/7');
    expect(getTenantOnboarding).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole('button', { name: 'Refrescar' }));
    await waitFor(() => expect(getTenantOnboarding).toHaveBeenCalledTimes(2));
  });

  it('verifyOnboardingStep failure surfaces an error notice', async () => {
    verifyOnboardingStep.mockReset();
    verifyOnboardingStep.mockRejectedValueOnce(new Error('verify-fail'));
    setup();
    await screen.findByText('Progreso: 3/7');

    const verifyButtons = screen.getAllByRole('button', { name: 'Verificar' });
    await userEvent.click(verifyButtons[verifyButtons.length - 1]);

    expect(await screen.findByText('verify-fail')).toBeInTheDocument();
  });
});
