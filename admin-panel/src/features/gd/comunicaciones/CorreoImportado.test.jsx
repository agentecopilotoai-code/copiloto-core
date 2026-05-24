import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listCorreosImportados: vi.fn(),
  getCorreoImportado: vi.fn(),
  convertirCorreoARadicado: vi.fn(),
  descartarCorreo: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { CorreoImportado } from './CorreoImportado.jsx';

const ROLES = ['gd.radicador'];
const C = {
  id: 'c1', asunto: 'Solicitud certificación',
  remitente: 'ciudadano@x.com', destinatario: 'ventanilla@entidad.gov.co',
  recibido_en: '2026-05-23T10:00:00Z', estado: 'pendiente',
  leido: false, cuerpo: 'Texto del correo',
  adjuntos: [{ nombre: 'cedula.pdf', size_kb: 120, url: 'https://x/y.pdf' }],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listCorreosImportados.mockResolvedValue({ items: [C], total: 1 });
  api.getCorreoImportado.mockResolvedValue(C);
});

describe('CorreoImportado', () => {
  it('sin permiso muestra warning', () => {
    render(<CorreoImportado session={{ token: 't' }} roles={['gd.firmante']} />);
    expect(screen.getByTestId('cor-no-perm')).toBeInTheDocument();
  });

  it('lista correos + click muestra detalle', async () => {
    const user = userEvent.setup();
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('cor-row'));
    await user.click(screen.getByTestId('cor-row'));
    await waitFor(() => expect(screen.getByTestId('cor-detalle')).toBeInTheDocument());
    expect(screen.getByTestId('cor-cuerpo').textContent).toMatch(/Texto del correo/);
    expect(screen.getByTestId('cor-adjuntos')).toBeInTheDocument();
  });

  it('empty', async () => {
    api.listCorreosImportados.mockResolvedValue({ items: [], total: 0 });
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('cor-empty')).toBeInTheDocument());
  });

  it('error', async () => {
    api.listCorreosImportados.mockRejectedValue(new Error('e'));
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('convertir a radicado', async () => {
    api.convertirCorreoARadicado.mockResolvedValue({ id: 'r1' });
    const user = userEvent.setup();
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cor-row'));
    await user.click(await screen.findByTestId('cor-convertir'));
    await user.click(screen.getByTestId('cor-conv-submit'));
    await waitFor(() => expect(api.convertirCorreoARadicado).toHaveBeenCalled());
  });

  it('convertir error', async () => {
    api.convertirCorreoARadicado.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cor-row'));
    await user.click(await screen.findByTestId('cor-convertir'));
    await user.click(screen.getByTestId('cor-conv-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('descartar con motivo', async () => {
    api.descartarCorreo.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cor-row'));
    await user.click(await screen.findByTestId('cor-descartar'));
    fireEvent.change(screen.getByLabelText(/Motivo del descarte/i), { target: { value: 'spam evidente' } });
    await user.click(screen.getByTestId('cor-descartar-submit'));
    await waitFor(() => expect(api.descartarCorreo).toHaveBeenCalled());
  });

  it('correo no pendiente oculta CTAs', async () => {
    api.getCorreoImportado.mockResolvedValue({ ...C, estado: 'convertido' });
    const user = userEvent.setup();
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cor-row'));
    await waitFor(() => screen.getByTestId('cor-detalle'));
    expect(screen.queryByTestId('cor-convertir')).toBeNull();
    expect(screen.queryByTestId('cor-descartar')).toBeNull();
  });

  it('filtros disparan refetch', async () => {
    render(<CorreoImportado session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(api.listCorreosImportados).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId('cor-filter-q'), { target: { value: 'cert' } });
    fireEvent.change(screen.getByTestId('cor-filter-estado'), { target: { value: 'convertido' } });
    await waitFor(() => expect(api.listCorreosImportados).toHaveBeenCalledTimes(3));
  });
});
