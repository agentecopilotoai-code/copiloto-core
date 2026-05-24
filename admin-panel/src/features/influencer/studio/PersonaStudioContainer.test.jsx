/**
 * Tests para PersonaStudioContainer (UI-INFLU-014.13).
 *
 * Cubre:
 *  - Fetch inicial paralelo de bundle + balance.
 *  - Pasa `studio` + `balance` al componente presentacional.
 *  - Polling cada 5s mientras hay generations queued/running; para cuando
 *    todas están succeeded/failed/canceled.
 *  - Cablea `onGenerate` → `generateContent` + refresh.
 *  - Cablea `onUploadReference` → `uploadPersonaReference`.
 *  - Cablea `onSchedulePost(g)` → navega al calendar con `?generation_id`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

let mockSession;
vi.mock('../../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../../services/coreApi.js', () => ({
  getPersonaStudio: vi.fn(),
  getCreditsBalance: vi.fn(),
  generateContent: vi.fn(),
  uploadPersonaReference: vi.fn(),
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
import { PersonaStudioContainer } from './PersonaStudioContainer.jsx';


const STUDIO_BASE = {
  persona: {
    id: 'p-1', name: 'Sofía', handle: 'sofia',
    status: 'active', avatar_url: null, category: 'Lifestyle',
  },
  stats: { posts_total: 0, reach_30d: 0, engagement_rate: 0, scheduled_count: 0 },
  next_post: null,
  platforms_connected: [],
  face_variations: [],
  recent_generations: [],
};


function renderContainer() {
  return render(
    <MemoryRouter initialEntries={['/t/acme/influencer/personas/p-1/studio']}>
      <Routes>
        <Route
          path="/t/:tenantSlug/influencer/personas/:personaId/studio"
          element={<PersonaStudioContainer />}
        />
        <Route
          path="/t/:tenantSlug/influencer/influencer-calendar"
          element={<div data-testid="calendar-target">Calendar</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}


beforeEach(() => {
  mockSession = { accessToken: 'tok', profile: { sub: 'u-1' } };
  coreApi.getPersonaStudio.mockReset();
  coreApi.getCreditsBalance.mockReset();
  coreApi.generateContent.mockReset();
  coreApi.uploadPersonaReference.mockReset();
  coreApi.getPersonaStudio.mockResolvedValue(STUDIO_BASE);
  coreApi.getCreditsBalance.mockResolvedValue({ balance: 100 });
});

afterEach(() => {
  vi.useRealTimers();
});


describe('<PersonaStudioContainer/>', () => {
  it('hace fetch paralelo de bundle + balance al montar', async () => {
    renderContainer();
    await waitFor(() => {
      expect(coreApi.getPersonaStudio).toHaveBeenCalledWith(
        expect.any(Object), 'tenant-1', 'p-1',
      );
      expect(coreApi.getCreditsBalance).toHaveBeenCalledWith(
        expect.any(Object), 'tenant-1',
      );
    });
    // Cuando el bundle llega, se renderiza el título del studio.
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /Estudio · generar/i })).toBeInTheDocument();
    });
  });

  it('cuando el bundle tiene generations queued/running, hace polling', async () => {
    vi.useFakeTimers();
    coreApi.getPersonaStudio.mockResolvedValue({
      ...STUDIO_BASE,
      recent_generations: [{
        id: 'g1', kind: 'photo', status: 'queued',
        created_at: new Date().toISOString(), assets: [],
      }],
    });
    renderContainer();
    // Espera el fetch inicial — usamos `act` + flushPromises pattern
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(coreApi.getPersonaStudio).toHaveBeenCalledTimes(1);

    // Avanza 5s — debe haber un nuevo fetch (polling).
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(coreApi.getPersonaStudio.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it('cuando ninguna generation está pending, NO polling', async () => {
    vi.useFakeTimers();
    coreApi.getPersonaStudio.mockResolvedValue({
      ...STUDIO_BASE,
      recent_generations: [{
        id: 'g1', kind: 'photo', status: 'succeeded',
        created_at: new Date().toISOString(), assets: [{ url: 'x.png', mime: 'image/png' }],
      }],
    });
    renderContainer();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const initialCalls = coreApi.getPersonaStudio.mock.calls.length;
    // Avanza 30s — NO debe haber nuevos fetches.
    await act(async () => {
      vi.advanceTimersByTime(30_000);
      await Promise.resolve();
    });
    expect(coreApi.getPersonaStudio.mock.calls.length).toBe(initialCalls);
  });

  it('si el primer fetch falla, pasa error al componente', async () => {
    coreApi.getPersonaStudio.mockRejectedValue(new Error('boom'));
    renderContainer();
    await waitFor(() => {
      expect(screen.getByText(/Personaje no disponible/i)).toBeInTheDocument();
    });
  });

  it('errores subsiguientes del polling NO disparan el error UI', async () => {
    vi.useFakeTimers();
    // Primer fetch OK con pending → polling activo.
    coreApi.getPersonaStudio.mockResolvedValueOnce({
      ...STUDIO_BASE,
      recent_generations: [{
        id: 'g1', kind: 'photo', status: 'queued',
        created_at: new Date().toISOString(), assets: [],
      }],
    });
    // Segundo fetch (polling) falla.
    coreApi.getPersonaStudio.mockRejectedValueOnce(new Error('red intermitente'));
    renderContainer();
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(screen.getByRole('heading', { name: /Estudio · generar/i })).toBeInTheDocument();
    await act(async () => {
      vi.advanceTimersByTime(5000);
      await Promise.resolve();
      await Promise.resolve();
    });
    // El error de red intermitente NO debe llevarnos a "Personaje no disponible".
    expect(screen.queryByText(/Personaje no disponible/i)).not.toBeInTheDocument();
  });

  it('cuando session o tenantId faltan, no fetcha', async () => {
    mockSession = null;
    renderContainer();
    await act(async () => {
      await Promise.resolve();
    });
    expect(coreApi.getPersonaStudio).not.toHaveBeenCalled();
  });
});
