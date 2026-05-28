import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listReglasAutoClasif: vi.fn(),
  crearReglaAutoClasif: vi.fn(),
  actualizarReglaAutoClasif: vi.fn(),
  eliminarReglaAutoClasif: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { ReglasAutoClasif } from './ReglasAutoClasif.jsx';

const REGLAS = {
  items: [
    { id: 'r1', nombre: 'PQRSD subject', prioridad: 100,
      condiciones: [{ campo: 'asunto', op: 'contiene', valor: 'PQRSD' }],
      accion: { tipo: 'cola', cola_destino: 'pqrsd' },
      activa: true, hits: 23 },
    { id: 'r2', nombre: 'Spam descarte', prioridad: 10,
      condiciones: [{ campo: 'remitente', op: 'contiene', valor: 'noreply@spam' }],
      accion: { tipo: 'descartar' },
      activa: false, hits: 0 },
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  api.listReglasAutoClasif.mockResolvedValue(REGLAS);
});

describe('ReglasAutoClasif', () => {
  it('admin sistema ve tabla', async () => {
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => expect(screen.getAllByTestId('cor-reglas-row')).toHaveLength(2));
  });

  it('coordinador VU ve aviso readonly aunque tenga RW (no aplica)', async () => {
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.profesional']} />);
    await waitFor(() => expect(screen.getByTestId('cor-reglas-readonly')).toBeInTheDocument());
  });

  it('abre modal nueva regla y guarda', async () => {
    api.crearReglaAutoClasif.mockResolvedValue({ id: 'r3' });
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-reglas-nueva'));
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.type(screen.getByTestId('cor-reglas-edit-nombre'), 'Test regla');
    await user.click(screen.getByTestId('cor-reglas-edit-guardar'));
    await waitFor(() => expect(api.crearReglaAutoClasif).toHaveBeenCalled());
  });

  it('agrega y borra condición', async () => {
    api.crearReglaAutoClasif.mockResolvedValue({ id: 'r3' });
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.click(screen.getByTestId('cor-reglas-cond-add'));
    expect(screen.getAllByTestId('cor-reglas-cond')).toHaveLength(2);
    await user.click(screen.getAllByTestId('cor-reglas-cond-rm')[0]);
    expect(screen.getAllByTestId('cor-reglas-cond')).toHaveLength(1);
  });

  it('edita condición existente (campo/op/valor)', async () => {
    api.crearReglaAutoClasif.mockResolvedValue({ id: 'r3' });
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.type(screen.getByTestId('cor-reglas-edit-nombre'), 'X');
    await user.selectOptions(screen.getByTestId('cor-reglas-cond-campo'), 'remitente');
    await user.selectOptions(screen.getByTestId('cor-reglas-cond-op'), 'igual');
    await user.type(screen.getByTestId('cor-reglas-cond-valor'), 'foo@bar.com');
    await user.click(screen.getByTestId('cor-reglas-edit-guardar'));
    await waitFor(() => expect(api.crearReglaAutoClasif).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        condiciones: expect.arrayContaining([
          expect.objectContaining({ campo: 'remitente', op: 'igual', valor: 'foo@bar.com' }),
        ]),
      }),
    ));
  });

  it('cambio de acción a descartar oculta destino', async () => {
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.selectOptions(screen.getByTestId('cor-reglas-accion-tipo'), 'descartar');
    expect(screen.queryByTestId('cor-reglas-accion-dest')).toBeNull();
  });

  it('editar regla existente', async () => {
    api.actualizarReglaAutoClasif.mockResolvedValue({ id: 'r1' });
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getAllByTestId('cor-reglas-editar'));
    await user.click(screen.getAllByTestId('cor-reglas-editar')[0]);
    await user.click(screen.getByTestId('cor-reglas-edit-activa'));
    await user.click(screen.getByTestId('cor-reglas-edit-guardar'));
    await waitFor(() => expect(api.actualizarReglaAutoClasif).toHaveBeenCalled());
  });

  it('borrar regla', async () => {
    api.eliminarReglaAutoClasif.mockResolvedValue({});
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getAllByTestId('cor-reglas-borrar'));
    await user.click(screen.getAllByTestId('cor-reglas-borrar')[0]);
    await waitFor(() => expect(api.eliminarReglaAutoClasif).toHaveBeenCalled());
  });

  it('error borrar', async () => {
    api.eliminarReglaAutoClasif.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getAllByTestId('cor-reglas-borrar'));
    await user.click(screen.getAllByTestId('cor-reglas-borrar')[0]);
    await waitFor(() => screen.getByTestId('cor-reglas-feedback'));
  });

  it('cancelar modal', async () => {
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.click(screen.getByTestId('cor-reglas-edit-cancelar'));
    expect(screen.queryByTestId('cor-reglas-modal')).toBeNull();
  });

  it('error al guardar', async () => {
    api.crearReglaAutoClasif.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await user.click(screen.getByTestId('cor-reglas-nueva'));
    await user.type(screen.getByTestId('cor-reglas-edit-nombre'), 'X');
    await user.click(screen.getByTestId('cor-reglas-edit-guardar'));
    await waitFor(() => expect(screen.getByTestId('cor-reglas-feedback').textContent).toMatch(/boom/));
  });

  it('empty', async () => {
    api.listReglasAutoClasif.mockResolvedValue({ items: [] });
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-reglas-empty'));
  });

  it('error de carga', async () => {
    api.listReglasAutoClasif.mockRejectedValue(new Error('e'));
    render(<ReglasAutoClasif session={{ token: 't' }} roles={['gd.admin_sistema']} />);
    await waitFor(() => screen.getByTestId('cor-reglas-error'));
  });
});
