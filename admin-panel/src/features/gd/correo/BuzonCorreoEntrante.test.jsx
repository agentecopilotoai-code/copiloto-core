import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listCorreoEntrante: vi.fn(),
  getCorreoEntrante: vi.fn(),
  convertirCorreoARadicado: vi.fn(),
  descartarCorreo: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { BuzonCorreoEntrante } from './BuzonCorreoEntrante.jsx';

const ROLES_RW = ['gd.radicador'];

beforeEach(() => {
  vi.clearAllMocks();
  api.listCorreoEntrante.mockResolvedValue({
    items: [
      { id: 'e1', remitente: 'a@b.com', asunto: 'Solicitud',
        snippet: 'Hola...', recibido_en: '2026-05-27T10:00:00Z',
        estado: 'nuevo' },
      { id: 'e2', remitente: 'c@d.com', asunto: 'Otra',
        recibido_en: '2026-05-27T09:00:00Z', estado: 'radicado' },
    ],
    total: 2,
  });
});

describe('BuzonCorreoEntrante', () => {
  it('sin permiso → aviso', () => {
    render(<BuzonCorreoEntrante session={{}} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('cor-bz-no-perm')).toBeInTheDocument();
  });

  it('lista items', async () => {
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => expect(screen.getAllByTestId('cor-bz-item')).toHaveLength(2));
  });

  it('selecciona item → preview', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'Solicitud', remitente: 'a@b.com',
      destinatarios: ['ventanilla@org'],
      cuerpo_texto: 'Texto plano', adjuntos: [{ nombre: 'doc.pdf', tamano: 1024 }],
      ya_radicado: false,
    });
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-cuerpo'));
    expect(screen.getByTestId('cor-bz-adjuntos').children).toHaveLength(1);
  });

  it('preview con cuerpo_html', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'X', remitente: 'a@b.com',
      destinatarios: [], cuerpo_html: '<p>HTML</p>',
      adjuntos: [], ya_radicado: false,
    });
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-cuerpo'));
    expect(screen.getByText('HTML')).toBeInTheDocument();
  });

  it('abrir modal radicar y guardar', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'X', remitente: 'a@b.com',
      destinatarios: [], cuerpo_texto: 'x', adjuntos: [], ya_radicado: false,
    });
    api.convertirCorreoARadicado.mockResolvedValue({
      radicado_id: 'r1', numero: 'R-001',
    });
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-radicar'));
    await user.click(screen.getByTestId('cor-bz-radicar'));
    await user.type(screen.getByTestId('cor-bz-modal-dep'), 'jurídica');
    await user.click(screen.getByTestId('cor-bz-modal-guardar'));
    await waitFor(() => screen.getByTestId('cor-bz-feedback'));
    expect(api.convertirCorreoARadicado).toHaveBeenCalled();
  });

  it('cancelar modal', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'X', remitente: 'a@b.com',
      destinatarios: [], cuerpo_texto: 'x', adjuntos: [], ya_radicado: false,
    });
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-radicar'));
    await user.click(screen.getByTestId('cor-bz-radicar'));
    await user.click(screen.getByTestId('cor-bz-modal-cancelar'));
    expect(screen.queryByTestId('cor-bz-modal')).toBeNull();
  });

  it('error al radicar', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'X', remitente: 'a@b.com',
      destinatarios: [], cuerpo_texto: 'x', adjuntos: [], ya_radicado: false,
    });
    api.convertirCorreoARadicado.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-radicar'));
    await user.click(screen.getByTestId('cor-bz-radicar'));
    await user.type(screen.getByTestId('cor-bz-modal-dep'), 'dep');
    await user.click(screen.getByTestId('cor-bz-modal-guardar'));
    await waitFor(() => expect(screen.getByTestId('cor-bz-feedback').textContent).toMatch(/boom/));
  });

  it('item ya radicado muestra link', async () => {
    api.getCorreoEntrante.mockResolvedValue({
      id: 'e1', asunto: 'X', remitente: 'a@b.com',
      destinatarios: [], cuerpo_texto: 'x', adjuntos: [],
      ya_radicado: true, radicado_id: 'r99',
    });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW}
      onNavigate={onNavigate} />);
    await waitFor(() => screen.getAllByTestId('cor-bz-item'));
    await user.click(screen.getAllByTestId('cor-bz-item')[0]);
    await waitFor(() => screen.getByTestId('cor-bz-ir-radicado'));
    await user.click(screen.getByTestId('cor-bz-ir-radicado'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/ventanilla/radicados/r99');
  });

  it('filtros disparan refetch', async () => {
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getByTestId('cor-bz-filtros'));
    await user.type(screen.getByTestId('cor-bz-asunto'), 'sol');
    await waitFor(() => expect(api.listCorreoEntrante).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ asunto: 'sol' }),
    ));
  });

  it('cambio de estado en filtro', async () => {
    const user = userEvent.setup();
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getByTestId('cor-bz-estado'));
    await user.selectOptions(screen.getByTestId('cor-bz-estado'), 'nuevo');
    await waitFor(() => expect(api.listCorreoEntrante).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ estado: 'nuevo' }),
    ));
  });

  it('error de bandeja', async () => {
    api.listCorreoEntrante.mockRejectedValue(new Error('e'));
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getByTestId('cor-bz-error'));
  });

  it('empty', async () => {
    api.listCorreoEntrante.mockResolvedValue({ items: [], total: 0 });
    render(<BuzonCorreoEntrante session={{ token: 't' }} roles={ROLES_RW} />);
    await waitFor(() => screen.getByTestId('cor-bz-empty'));
  });
});
