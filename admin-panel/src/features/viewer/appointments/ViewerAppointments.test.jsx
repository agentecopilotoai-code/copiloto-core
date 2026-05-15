import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

// Aislamos `coreApi` para no arrastrar todo el grafo del módulo. El feature
// sólo necesita `listAppointments` (tenant-scoped server-side).
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
import { ViewerAppointments } from './ViewerAppointments.jsx';

const VIEWER_PROFILE = { sub: 'u-viewer' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['viewer'] };
const SESSION = { accessToken: 'tok' };
const MODULE = { label: 'Citas', summary: 'Lectura' };

const APPOINTMENTS = [
  {
    id: 'a1',
    starts_at: '2026-05-14T11:00:00Z',
    status: 'confirmed',
    service_name: 'Botox frontal',
    resource_name: 'Dra. Sofía',
    contact_label: 'María José L.',
  },
  {
    id: 'a2',
    starts_at: '2026-05-15T09:00:00Z',
    status: 'completed',
    service_name: 'Peeling',
    resource_name: 'Dra. Sofía',
    contact_label: 'Andrés Gómez',
  },
  {
    id: 'a3',
    starts_at: '2026-05-16T10:00:00Z',
    status: 'pending',
    service_name: 'Limpieza facial · paquete',
    resource_name: 'Dra. Laura',
    contact_label: 'Diego Castro',
  },
];

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <ViewerAppointments module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: VIEWER_PROFILE };
  coreApi.listAppointments.mockResolvedValue(APPOINTMENTS);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ViewerAppointments', () => {
  it('renderiza el listado paginado + filtros + botón de exportar para un viewer', async () => {
    setup();

    // El PageHeader del feature, el formulario de filtros y la card de
    // «Filtros» deben estar presentes.
    expect(
      screen.getByRole('heading', { name: 'Citas', level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Exportar CSV' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Limpiar filtros' })).toBeInTheDocument();

    // Una vez resuelve `listAppointments`, las tarjetas se pintan vía
    // `AppointmentCard` (que pinta el `service_name` como título y un
    // `StatusBadge` con el `status` crudo).
    await waitFor(() => {
      expect(screen.getByText('Botox frontal')).toBeInTheDocument();
    });
    expect(screen.getByText('Peeling')).toBeInTheDocument();
    expect(screen.getByText('Limpieza facial · paquete')).toBeInTheDocument();
    expect(coreApi.listAppointments).toHaveBeenCalledWith(SESSION, 'tenant-acme');

    // No se renderizan acciones de fila (criterio UI-010): ni «Tomar handoff»
    // ni «Reagendar» ni «Confirmar» — los Viewers son solo lectura.
    expect(screen.queryByRole('button', { name: /Tomar handoff/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Reagendar/i })).toBeNull();
    expect(screen.queryByRole('button', { name: /Confirmar/i })).toBeNull();
  });

  it('aplica un filtro de status y reduce la lista visible', async () => {
    setup();

    await waitFor(() => {
      expect(screen.getByText('Botox frontal')).toBeInTheDocument();
    });

    // El <select> de estado tiene el label «Estado»; lo localizamos por label.
    const statusSelect = screen.getByLabelText('Estado');
    fireEvent.change(statusSelect, { target: { value: 'pending' } });

    // Sólo la cita "Limpieza facial · paquete" (status pending) debe quedar.
    await waitFor(() => {
      expect(screen.getByText('Limpieza facial · paquete')).toBeInTheDocument();
    });
    expect(screen.queryByText('Botox frontal')).toBeNull();
    expect(screen.queryByText('Peeling')).toBeNull();
  });

  it('exportar CSV dispara URL.createObjectURL con un Blob CSV', async () => {
    // jsdom no implementa `URL.createObjectURL` ni `revokeObjectURL` por
    // defecto — los asignamos como mocks de Vitest antes de espiarlos. El test
    // verifica que el helper construye un `Blob` con el mime type
    // `text/csv;charset=utf-8` y agenda la descarga.
    const createMock = vi.fn(() => 'blob:mock-url');
    const revokeMock = vi.fn();
    URL.createObjectURL = createMock;
    URL.revokeObjectURL = revokeMock;
    // Evitamos abrir un download real durante el test.
    const clickSpy = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(() => {});

    try {
      setup();
      await waitFor(() => {
        expect(screen.getByText('Botox frontal')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: 'Exportar CSV' }));

      expect(createMock).toHaveBeenCalledTimes(1);
      const blob = createMock.mock.calls[0][0];
      expect(blob).toBeInstanceOf(Blob);
      expect(blob.type).toBe('text/csv;charset=utf-8');
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(revokeMock).toHaveBeenCalledWith('blob:mock-url');
    } finally {
      // Limpieza para no contaminar otros tests del archivo.
      delete URL.createObjectURL;
      delete URL.revokeObjectURL;
    }
  });

  it('renderiza AccessDenied cuando el rol del tenant carece de appointments.view', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: [] } });
    // `RequirePermission` corta el árbol antes del orquestador y muestra el
    // mensaje «Acceso restringido». El listado y el heading no se montan.
    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Citas', level: 1 }),
    ).toBeNull();
    // Nota: el hook `useViewerAppointmentsData` se invoca antes del gate de
    // permisos (igual que en `today-appointments` y `audit`), por lo que sí
    // se dispara una llamada a `listAppointments` aunque el árbol del feature
    // nunca se renderice. El backend reverifica con JWT + RLS — la respuesta
    // se descarta sin pintarse en pantalla.
  });
});
