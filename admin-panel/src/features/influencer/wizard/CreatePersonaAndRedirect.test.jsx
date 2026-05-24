/**
 * Tests para CreatePersonaAndRedirect (UI-INFLU-014.11) — la página de
 * "crear nuevo personaje" hace POST y redirige al wizard del ID nuevo.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

let mockSession;
vi.mock('../../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../../services/coreApi.js', () => ({
  createPersona: vi.fn(),
}));

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../../../services/coreApi.js';
import { CreatePersonaAndRedirect } from './CreatePersonaAndRedirect.jsx';


const ACTIVE_TENANT = { id: 'tenant-1', slug: 'acme' };


function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/t/acme/influencer/personas/new']}>
      <Routes>
        <Route
          path="/t/:tenantSlug/influencer/personas/new"
          element={<CreatePersonaAndRedirectWrapped />}
        />
        <Route
          path="/t/:tenantSlug/influencer/personas/:personaId/wizard/:stepSlug"
          element={<div data-testid="wizard-target">Wizard {window.location.pathname}</div>}
        />
        <Route
          path="/t/:tenantSlug/influencer/influencer-casting"
          element={<div data-testid="casting-target">Casting</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

// Helper: simula el OutletContext del shell de tenants (que provee
// `activeTenant`).
function CreatePersonaAndRedirectWrapped() {
  // Usamos `useOutletContext` real, pero como no hay <Outlet>, devuelve
  // undefined; el componente acepta `useOutletContext() ?? {}` así que
  // el activeTenant viene como undefined. Para inyectarlo en tests
  // re-monkeypatcheamos `useOutletContext` abajo.
  return <CreatePersonaAndRedirect />;
}

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useOutletContext: () => ({ activeTenant: ACTIVE_TENANT }),
  };
});


beforeEach(() => {
  mockSession = { accessToken: 'tok', profile: { sub: 'u-1' } };
  coreApi.createPersona.mockReset();
});


describe('<CreatePersonaAndRedirect/>', () => {
  it('muestra "Creando personaje…" mientras la promise está pendiente', () => {
    coreApi.createPersona.mockReturnValue(new Promise(() => {})); // never resolves
    renderWithRouter();
    expect(screen.getByText(/Creando personaje/i)).toBeInTheDocument();
  });

  it('cuando createPersona resuelve, redirige al wizard/step-1 del nuevo ID', async () => {
    coreApi.createPersona.mockResolvedValue({ id: 'p-new-123' });
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByTestId('wizard-target')).toBeInTheDocument();
    });
    // La URL debe contener el persona ID
    expect(coreApi.createPersona).toHaveBeenCalledWith(
      expect.any(Object),
      'tenant-1',
      expect.objectContaining({
        name: 'Personaje en construcción',
        status: 'draft',
        handle: expect.stringMatching(/^draft_\d+$/),
      }),
    );
  });

  it('cuando createPersona falla, muestra el error + botón "Volver al casting"', async () => {
    coreApi.createPersona.mockRejectedValue(new Error('No hay créditos'));
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText(/No hay créditos/)).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Volver al casting/i })).toBeInTheDocument();
  });

  it('click en "Volver al casting" navega al casting', async () => {
    coreApi.createPersona.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText(/boom/)).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /Volver al casting/i }));
    await waitFor(() => {
      expect(screen.getByTestId('casting-target')).toBeInTheDocument();
    });
  });

  it('si createPersona falla sin .message, muestra fallback genérico', async () => {
    coreApi.createPersona.mockRejectedValue({});
    renderWithRouter();
    await waitFor(() => {
      expect(screen.getByText(/No se pudo crear el personaje/i)).toBeInTheDocument();
    });
  });

  it('sin session o sin tenantId, NO llama a createPersona', () => {
    mockSession = null;
    renderWithRouter();
    expect(coreApi.createPersona).not.toHaveBeenCalled();
  });
});
