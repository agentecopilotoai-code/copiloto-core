import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';

// Mock coreApi to avoid pulling the whole module graph + real network.
vi.mock('../../../services/coreApi.js', () => ({
  getTenantReadiness: vi.fn(),
  markTenantLive: vi.fn(),
}));

let mockTenantContext;
vi.mock('../../../app/TenantProvider.jsx', () => ({
  useTenantContext: () => mockTenantContext,
  useOptionalTenantContext: () => mockTenantContext,
}));

// eslint-disable-next-line import/first
import * as coreApi from '../../../services/coreApi.js';
// eslint-disable-next-line import/first
import { GoLiveReadiness } from './GoLiveReadiness.jsx';

const OWNER_PROFILE = { sub: 'u-owner' };
const ACME = { id: 'tenant-acme', slug: 'acme', roles: ['owner'] };
const SESSION = { accessToken: 'tok' };
const MODULE = {
  label: 'Go-live Readiness',
  summary: 'Checklist automatizado para validar si un tenant puede entrar a producción.',
};

const READY_REPORT = {
  tenant_id: 'tenant-acme',
  ready: true,
  status: 'ready',
  reasons: [],
  checked_at: '2026-05-15T12:00:00Z',
  checks: [
    { key: 'tenant_active', ready: true, label: 'Tenant en estado live', reason: 'status = live · plan Pro', details: { plan: 'Pro' } },
    { key: 'whatsapp_channel', ready: true, label: 'phone_number_id y firma HMAC verificados', reason: 'webhook recibió evento de prueba · firma ok', details: { delivery_mode_live: true } },
    { key: 'knowledge_retrieval', ready: true, label: 'Knowledge studio con ≥ 1 documento activo', reason: '4 documentos · 130 chunks indexados' },
    { key: 'handoff', ready: true, label: 'Handoff humano funcional · test E2E', reason: 'escalation_test ok hace 3h' },
    { key: 'audit', ready: true, label: 'Auditoría capturando eventos', reason: '1,240 eventos en últimos 7d' },
  ],
};

const PENDING_REPORT = {
  ...READY_REPORT,
  ready: false,
  status: 'not_ready',
  reasons: ['handoff_pending'],
  checks: [
    ...READY_REPORT.checks.slice(0, 4),
    { key: 'audit', ready: false, label: 'Auditoría capturando eventos', reason: 'Sin eventos recientes' },
  ],
};

function setup({ tenant = ACME } = {}) {
  return render(
    <MemoryRouter>
      <GoLiveReadiness module={MODULE} session={SESSION} tenant={tenant} />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockTenantContext = { session: SESSION, profile: OWNER_PROFILE };
  coreApi.getTenantReadiness.mockResolvedValue(READY_REPORT);
  coreApi.markTenantLive.mockResolvedValue({
    ...READY_REPORT,
    tenant_status: { go_live_at: '2026-05-15T14:00:00Z' },
  });
});

describe('GoLiveReadiness', () => {
  it('renderiza el header, las secciones agrupadas y el contador "X / Y pasados"', async () => {
    setup();

    expect(
      await screen.findByRole('heading', { name: 'Go-live Readiness', level: 1 }),
    ).toBeInTheDocument();

    // Sección "Tenant activo y configurado" — primer check del payload.
    expect(await screen.findByText('Tenant activo y configurado')).toBeInTheDocument();
    expect(screen.getByText('Canal WhatsApp y templates')).toBeInTheDocument();
    expect(screen.getByText('Retrieval y políticas')).toBeInTheDocument();
    expect(screen.getByText('Operación y handoff')).toBeInTheDocument();

    // Counter chip "5 / 5 pasados" — todos los checks ready. El span padre
    // contiene el texto completo "Checklist · 5 / 5 pasados".
    const chip = screen.getByText(/^Checklist ·$/);
    expect(chip.parentElement?.textContent).toMatch(/5\s*\/\s*5/);
    // Badge "Listo" cuando 0 pendientes.
    expect(screen.getByText('Listo')).toBeInTheDocument();
  });

  it('renderiza badge "N / M" por sección y muestra el detalle de cada check', async () => {
    setup();

    // La sección "Operación y handoff" tiene 2 checks (handoff + audit) ambos
    // listos en el READY_REPORT — el badge específico de esa sección lo
    // diferencia del resto.
    expect(
      await screen.findByLabelText('2 de 2 checks pasados'),
    ).toBeInTheDocument();
    // Reason text del primer check.
    expect(screen.getByText('status = live · plan Pro')).toBeInTheDocument();
    // Detalle "plan: Pro" rendered from `details` map.
    expect(screen.getByText(/plan:\s*Pro/)).toBeInTheDocument();
  });

  it('botón "Marcar live" está habilitado cuando todos los checks pasan', async () => {
    setup();

    const button = await screen.findByRole('button', { name: /Marcar tenant como live/ });
    expect(button).toBeEnabled();
  });

  it('botón "Marcar live" está deshabilitado cuando hay checks pendientes', async () => {
    coreApi.getTenantReadiness.mockResolvedValue(PENDING_REPORT);
    setup();

    // Esperar a que cargue el reporte.
    await screen.findByText(/Sin eventos recientes/);

    const button = screen.getByRole('button', { name: /Marcar live deshabilitado: 1 check/ });
    expect(button).toBeDisabled();
    // Counter chip refleja 4 / 5.
    const chip = screen.getByText(/^Checklist ·$/);
    expect(chip.parentElement?.textContent).toMatch(/4\s*\/\s*5/);
    // Pill "1 pendiente".
    expect(screen.getByText('1 pendiente')).toBeInTheDocument();
  });

  it('click en "Marcar live" dispara markTenantLive y muestra el banner de éxito', async () => {
    setup();
    const button = await screen.findByRole('button', { name: /Marcar tenant como live/ });

    await userEvent.click(button);

    // useConfirm fallback (no ConfirmProvider) resuelve true automáticamente —
    // ver `useConfirm` en `ConfirmDialog.jsx`.
    await screen.findByText('Tenant marcado en producción.');
    expect(coreApi.markTenantLive).toHaveBeenCalledWith(SESSION, 'tenant-acme');
    // El reporte refrescado debe pintar la sección "Tenant en producción"
    // y deshabilitar el botón porque alreadyLive=true.
    const btnAfter = screen.getByRole('button', { name: /Tenant ya está en producción/ });
    expect(btnAfter).toBeDisabled();
    expect(btnAfter.textContent).toMatch(/En producción/);
  });

  it('respuesta 409 del backend muestra los reasons en un AlertBanner', async () => {
    const conflict = new Error('Tenant not ready for go-live');
    conflict.status = 409;
    conflict.detail = {
      message: 'Tenant not ready for go-live',
      reasons: ['Canal WhatsApp no está en modo live', 'Sin eventos de auditoría'],
    };
    coreApi.markTenantLive.mockRejectedValue(conflict);
    setup();
    const button = await screen.findByRole('button', { name: /Marcar tenant como live/ });

    await userEvent.click(button);

    expect(
      await screen.findByText('No se pudo marcar live: hay checks pendientes.'),
    ).toBeInTheDocument();
    expect(screen.getByText('Canal WhatsApp no está en modo live')).toBeInTheDocument();
    expect(screen.getByText('Sin eventos de auditoría')).toBeInTheDocument();
  });

  it('reporte ya marcado live renderiza el banner "Tenant en producción"', async () => {
    coreApi.getTenantReadiness.mockResolvedValue({
      ...READY_REPORT,
      tenant_status: { go_live_at: '2026-05-15T14:00:00Z' },
    });
    setup();

    await screen.findByText('Tenant en producción');
    expect(
      screen.getByRole('button', { name: /Tenant ya está en producción/ }),
    ).toBeDisabled();
    // markTenantLive NO se llama por sí solo (solo on-click).
    expect(coreApi.markTenantLive).not.toHaveBeenCalled();
  });

  it('rol admin (sin mark_live) ve el banner "Solo el owner" y NO ve el botón Marcar live', async () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['admin'] } });

    expect(
      await screen.findByText('Solo el owner del negocio puede marcar live'),
    ).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Marcar tenant como live/ })).toBeNull();
    expect(screen.queryByRole('button', { name: /Marcar live/ })).toBeNull();
  });

  it('AccessDenied cuando el rol del tenant no tiene go_live_readiness.read', () => {
    setup({ tenant: { id: 'tenant-acme', slug: 'acme', roles: ['agent'] } });

    expect(screen.getByText(/Acceso restringido/i)).toBeInTheDocument();
    expect(
      screen.queryByRole('heading', { name: 'Go-live Readiness', level: 1 }),
    ).toBeNull();
  });

  it('click en "Exportar checklist" dispara la descarga client-side de un CSV', async () => {
    // `URL.createObjectURL` no existe por defecto en jsdom — lo stubbeamos.
    const originalCreate = URL.createObjectURL;
    const originalRevoke = URL.revokeObjectURL;
    const createSpy = vi.fn(() => 'blob:fake');
    const revokeSpy = vi.fn();
    URL.createObjectURL = createSpy;
    URL.revokeObjectURL = revokeSpy;
    // jsdom no implementa `HTMLAnchorElement.prototype.click` con descarga; stub.
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    try {
      setup();
      const exportBtn = await screen.findByRole('button', { name: 'Exportar checklist' });

      await userEvent.click(exportBtn);

      expect(createSpy).toHaveBeenCalledTimes(1);
      expect(clickSpy).toHaveBeenCalledTimes(1);
      expect(revokeSpy).toHaveBeenCalledTimes(1);
    } finally {
      URL.createObjectURL = originalCreate;
      URL.revokeObjectURL = originalRevoke;
      clickSpy.mockRestore();
    }
  });

  it('error de carga del checklist se muestra como AlertBanner', async () => {
    coreApi.getTenantReadiness.mockRejectedValue(new Error('Backend caído'));
    setup();

    expect(await screen.findByText('Backend caído')).toBeInTheDocument();
  });
});
