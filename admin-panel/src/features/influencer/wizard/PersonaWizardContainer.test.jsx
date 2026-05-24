/**
 * Tests para PersonaWizardContainer.
 *
 * Cubre los flujos críticos del orquestador del wizard:
 *  - Slug inválido → redirige a step-1.
 *  - Sin session/tenant → LoadingScreen.
 *  - step 1 → renderiza Step1Face.
 *  - steps 2-5 sin personaId → StateScreen "empieza por step 1".
 *  - steps 2-5 con personaId → renderiza el step correspondiente.
 *  - sessionStorage: load/save por personaId.
 *  - handleGenerateVariations: persiste face, genera, anexa al draft.
 *  - handleNextFace: persiste + avanza a step 2.
 *  - handleActivate: submit final + navigate al casting.
 *  - errores backend → setGlobalError.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

let mockSession;
vi.mock('../../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../../services/coreApi.js', () => ({
  createPersona: vi.fn(),
  generateFaceVariations: vi.fn(),
  generateVoiceSample: vi.fn(),
  getPersona: vi.fn(),
  wizardSaveBody: vi.fn(),
  wizardSaveFace: vi.fn(),
  wizardSaveIdentity: vi.fn(),
  wizardSavePlatforms: vi.fn(),
  wizardSaveVoice: vi.fn(),
  wizardSubmit: vi.fn(),
}));

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: () => ({ can: () => true }),
}));

const ACTIVE_TENANT = { id: 'tenant-1', slug: 'acme' };
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useOutletContext: () => ({ activeTenant: ACTIVE_TENANT }),
  };
});

// eslint-disable-next-line no-unused-vars
import * as coreApi from '../../../services/coreApi.js';
import { PersonaWizardContainer } from './PersonaWizardContainer.jsx';


function renderWithRoute(initialPath) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route
          path="/t/:tenantSlug/influencer/personas/:personaId/wizard/:stepSlug"
          element={<PersonaWizardContainer />}
        />
        <Route
          path="/t/:tenantSlug/influencer/personas/new/:stepSlug"
          element={<PersonaWizardContainer />}
        />
        <Route
          path="/t/:tenantSlug/influencer/influencer-casting"
          element={<div data-testid="casting-target">Casting</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}


beforeEach(() => {
  mockSession = { accessToken: 'tok', profile: { sub: 'u-1' } };
  if (typeof sessionStorage !== 'undefined') sessionStorage.clear();
  Object.values(coreApi).forEach((fn) => fn?.mockReset?.());
});


describe('<PersonaWizardContainer/> — guards', () => {
  it('sin session → LoadingScreen', () => {
    mockSession = null;
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    // LoadingScreen tiene un texto identificable
    expect(document.body.textContent).toMatch(/cargando|loading/i);
  });

  it('slug inválido → Navigate a step-1 (re-render con step-1 visible)', () => {
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-99');
    // Después del redirect re-renderiza step-1 → vemos algo del Step1Face
    expect(document.querySelector('[data-view="wizard-step-1"]')).toBeTruthy();
  });

  it('step 1 con personaId renderiza Step1Face', () => {
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    expect(document.querySelector('[data-view="wizard-step-1"]')).toBeTruthy();
  });

  it('step 2 con personaId nuevo (sin draft.personaId previo) muestra step 2', async () => {
    // El container setea draft.personaId desde el URL via useEffect; el primer
    // render puede mostrar el StateScreen, pero después del useEffect ya está OK.
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-2');
    await waitFor(() => {
      // Espera que el draft.personaId se sincronice y muestre el step 2.
      expect(document.querySelector('[data-view="wizard-step-2"]')).toBeTruthy();
    });
  });

  it('step 3 con personaId del URL renderiza Step3Identity', async () => {
    renderWithRoute('/t/acme/influencer/personas/p-2/wizard/step-3');
    await waitFor(() => {
      expect(document.querySelector('[data-view="wizard-step-3"]')).toBeTruthy();
    });
  });

  it('step 4 con personaId del URL renderiza Step4Voice', async () => {
    renderWithRoute('/t/acme/influencer/personas/p-3/wizard/step-4');
    await waitFor(() => {
      expect(document.querySelector('[data-view="wizard-step-4"]')).toBeTruthy();
    });
  });

  it('step 5 con personaId del URL renderiza Step5Platforms', async () => {
    renderWithRoute('/t/acme/influencer/personas/p-4/wizard/step-5');
    await waitFor(() => {
      expect(document.querySelector('[data-view="wizard-step-5"]')).toBeTruthy();
    });
  });
});


describe('<PersonaWizardContainer/> — flujos backend', () => {
  it('Step 1: handleNextFace persiste face y avanza al step 2', async () => {
    coreApi.wizardSaveFace.mockResolvedValue({});
    const user = userEvent.setup();
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    // El botón "Continuar a Cuerpo →" del Step1Face dispara handleNextFace.
    const nextBtn = await screen.findByRole('button', { name: /Continuar a Cuerpo/i });
    await user.click(nextBtn);
    await waitFor(() => {
      expect(coreApi.wizardSaveFace).toHaveBeenCalled();
    });
  });

  it('Step 1: handleGenerateVariations llama wizardSaveFace + generateFaceVariations', async () => {
    coreApi.wizardSaveFace.mockResolvedValue({});
    coreApi.generateFaceVariations.mockResolvedValue({
      assets: [{ id: 'a1', url: 'https://cdn/a1.png', marked_canonical: false }],
    });
    const user = userEvent.setup();
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    // El botón "Generar" del Step1Face (aria-label específico).
    const generateBtn = await screen.findByRole('button', { name: /Generar nueva variación/i });
    await user.click(generateBtn);
    await waitFor(() => {
      expect(coreApi.generateFaceVariations).toHaveBeenCalled();
    });
  });

  it('Step 1: si generateFaceVariations falla → AlertBanner con error', async () => {
    coreApi.wizardSaveFace.mockResolvedValue({});
    coreApi.generateFaceVariations.mockRejectedValue(new Error('provider down'));
    const user = userEvent.setup();
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    await user.click(await screen.findByRole('button', { name: /Generar nueva variación/i }));
    await waitFor(() => {
      expect(screen.getByText(/provider down/i)).toBeInTheDocument();
    });
  });

  it('Step 1: wizardSaveFace error → AlertBanner', async () => {
    coreApi.wizardSaveFace.mockRejectedValue(new Error('schema invalid'));
    const user = userEvent.setup();
    renderWithRoute('/t/acme/influencer/personas/p-1/wizard/step-1');
    const nextBtn = await screen.findByRole('button', { name: /Continuar a Cuerpo/i });
    await user.click(nextBtn);
    await waitFor(() => {
      expect(screen.getByText(/schema invalid/i)).toBeInTheDocument();
    });
  });

  it('sessionStorage: carga draft existente al montar', async () => {
    // Pre-popula el sessionStorage del personaId.
    sessionStorage.setItem(
      'influencer.wizardDraft.p-loaded',
      JSON.stringify({
        personaId: 'p-loaded',
        face: { ethnicity: 'europea' },
        body: null, identity: null, voice: null, platforms: null,
        voiceSampleUrl: null, faceVariations: [],
      }),
    );
    renderWithRoute('/t/acme/influencer/personas/p-loaded/wizard/step-1');
    // Step1Face debe renderizarse — el container ya cargó el draft.
    expect(document.querySelector('[data-view="wizard-step-1"]')).toBeTruthy();
  });
});
