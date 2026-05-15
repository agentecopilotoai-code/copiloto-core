import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Avoid importing the real coreApi (which would drag in the full module graph).
vi.mock('../../../services/coreApi.js', () => ({
  listAppointments: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { TodayAppointments } from './TodayAppointments.jsx';
// eslint-disable-next-line import/first
import { todayISO, shiftDayISO } from './todayAppointmentsData.js';

const AGENT_PROFILE = { sub: 'u-agent' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['agent'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Citas del día', summary: 'Agenda del día' };

// Build ISO timestamps anchored to the local day so the client-side day filter
// is timezone-stable: noon local on the target day.
function atNoon(dayISO, hour = 12) {
  return new Date(`${dayISO}T${String(hour).padStart(2, '0')}:00:00`).toISOString();
}

const TODAY = todayISO();
const TOMORROW = shiftDayISO(TODAY, 1);

const APPOINTMENTS = [
  {
    id: 'appt-today-1',
    starts_at: atNoon(TODAY, 10),
    status: 'confirmed',
    service_name: 'Limpieza facial',
    resource_name: 'Dra. Pérez',
    payment_status: 'paid',
  },
  {
    id: 'appt-today-2',
    starts_at: atNoon(TODAY, 14),
    status: 'pending',
    service_name: 'Valoración inicial',
    resource_name: 'Dr. Rivas',
    payment_status: 'pending',
  },
  {
    id: 'appt-tomorrow-1',
    starts_at: atNoon(TOMORROW, 9),
    status: 'confirmed',
    service_name: 'Botox frontal',
    resource_name: 'Dr. Rivas',
    payment_status: 'not_required',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <TodayAppointments module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: AGENT_PROFILE };
  coreApi.listAppointments.mockResolvedValue(APPOINTMENTS);
});

describe('TodayAppointments', () => {
  it("renders today's appointments list and the summary tiles", async () => {
    setup();

    expect(
      screen.getByRole('heading', { name: 'Citas del día', level: 1 }),
    ).toBeInTheDocument();
    await waitFor(() => expect(coreApi.listAppointments).toHaveBeenCalled());

    // Today's two appointments are shown; tomorrow's is filtered out client-side.
    expect(await screen.findByText('Limpieza facial')).toBeInTheDocument();
    expect(screen.getByText('Valoración inicial')).toBeInTheDocument();
    expect(screen.queryByText('Botox frontal')).toBeNull();

    // Summary tiles derive counts from the day's list.
    expect(
      screen.getByRole('region', { name: 'Resumen de citas del día' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Sin confirmar')).toBeInTheDocument();
    expect(screen.getByText('Atendidas')).toBeInTheDocument();
  });

  it('navigating to "Mañana" re-filters the list to the next day', async () => {
    setup();
    await screen.findByText('Limpieza facial');

    await userEvent.click(screen.getByRole('button', { name: 'Mañana' }));

    // Now tomorrow's appointment shows and today's are filtered out.
    expect(await screen.findByText('Botox frontal')).toBeInTheDocument();
    expect(screen.queryByText('Limpieza facial')).toBeNull();
  });

  it('"Hoy" returns the list to the current day after navigating away', async () => {
    setup();
    await screen.findByText('Limpieza facial');

    await userEvent.click(screen.getByRole('button', { name: 'Mañana' }));
    await screen.findByText('Botox frontal');
    await userEvent.click(screen.getByRole('button', { name: 'Hoy' }));

    expect(await screen.findByText('Limpieza facial')).toBeInTheDocument();
    expect(screen.queryByText('Botox frontal')).toBeNull();
  });

  it('renders AccessDenied when the active tenant role lacks appointments.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Citas del día', level: 1 }),
    ).toBeNull();
  });
});
