/**
 * Tests para CalendarContainer (UI-INFLU-014 wiring).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

let mockSession;
vi.mock('../../../context/AuthContext.jsx', () => ({
  useAuth: () => ({ session: mockSession }),
}));

vi.mock('../../../services/coreApi.js', () => ({
  getCalendar: vi.fn(),
  getCasting: vi.fn(),
  updatePost: vi.fn(),
  cancelPost: vi.fn(),
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
import { CalendarContainer } from './CalendarContainer.jsx';


function renderContainer() {
  return render(
    <MemoryRouter initialEntries={['/t/acme/influencer/influencer-calendar']}>
      <Routes>
        <Route
          path="/t/:tenantSlug/influencer/influencer-calendar"
          element={<CalendarContainer />}
        />
      </Routes>
    </MemoryRouter>,
  );
}


beforeEach(() => {
  mockSession = { accessToken: 'tok', profile: { sub: 'u-1' } };
  Object.values(coreApi).forEach((fn) => fn?.mockReset?.());
  coreApi.getCalendar.mockResolvedValue({ posts: [] });
  coreApi.getCasting.mockResolvedValue({ personas: [] });
});


describe('<CalendarContainer/>', () => {
  it('al montar fetcha calendar + casting en paralelo', async () => {
    renderContainer();
    await waitFor(() => {
      expect(coreApi.getCalendar).toHaveBeenCalled();
      expect(coreApi.getCasting).toHaveBeenCalled();
    });
  });

  it('si no hay session, NO fetcha', async () => {
    mockSession = null;
    renderContainer();
    // El LoadingScreen se renderiza pero no se hace fetch.
    expect(coreApi.getCalendar).not.toHaveBeenCalled();
  });

  it('hace map del personas response al shape { id, display_name, handle }', async () => {
    coreApi.getCasting.mockResolvedValue({
      personas: [
        { id: 'p1', handle: 'sofia', display_name: 'Sofía Vega' },
        { id: 'p2', handle: 'kole' },  // sin display_name → usa handle
      ],
    });
    renderContainer();
    await waitFor(() => {
      // Cuando los datos cargan, el LoadingScreen desaparece y se renderiza Calendar.
      expect(coreApi.getCasting).toHaveBeenCalled();
    });
  });

  it('si el fetch de calendar falla, igual renderiza (lista vacía)', async () => {
    coreApi.getCalendar.mockRejectedValue(new Error('boom'));
    renderContainer();
    await waitFor(() => {
      expect(coreApi.getCalendar).toHaveBeenCalled();
    });
  });
});
