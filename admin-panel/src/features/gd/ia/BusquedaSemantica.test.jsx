import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  buscarSemanticoIa: vi.fn(),
  registrarFeedbackBusquedaIa: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { BusquedaSemantica } from './BusquedaSemantica.jsx';

const RESPUESTA = {
  resultados: [
    { documento_id: 'd1', titulo: 'Política X', fragmento: 'política sobre...', score: 0.92 },
    { documento_id: 'd2', titulo: 'Memo Y', fragmento: 'memorando interno...', score: 0.74, entidad: 'memorando' },
  ],
  modelo_embeddings: 'text-embedding-3-large', tokens: 200,
};

beforeEach(() => vi.clearAllMocks());

describe('BusquedaSemantica', () => {
  it('sin permiso muestra aviso', () => {
    render(<BusquedaSemantica session={{}} roles={[]} />);
    expect(screen.getByTestId('ia-bs-no-perm')).toBeInTheDocument();
  });

  it('busca y muestra resultados', async () => {
    api.buscarSemanticoIa.mockResolvedValue(RESPUESTA);
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'políticas');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => screen.getByTestId('ia-bs-resultados'));
    expect(screen.getAllByTestId('ia-bs-item')).toHaveLength(2);
  });

  it('cambia scope y topK', async () => {
    api.buscarSemanticoIa.mockResolvedValue({ resultados: [] });
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'X');
    await user.selectOptions(screen.getByTestId('ia-bs-scope'), 'mi_dependencia');
    // Number inputs son flaky con clear+type, usamos fireEvent.change directo.
    fireEvent.change(screen.getByTestId('ia-bs-topk'), { target: { value: '5' } });
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => expect(api.buscarSemanticoIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ query: 'X', scope: 'mi_dependencia', top_k: 5 }),
    ));
  });

  it('navega al hacer click en un item', async () => {
    api.buscarSemanticoIa.mockResolvedValue(RESPUESTA);
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']}
        onNavigate={onNavigate} />,
    );
    await user.type(screen.getByTestId('ia-bs-query'), 'políticas');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => screen.getByTestId('ia-bs-resultados'));
    await user.click(screen.getAllByTestId('ia-bs-item-link')[0]);
    expect(onNavigate).toHaveBeenCalledWith('/gd/documentos/d1');
  });

  it('feedback positivo', async () => {
    api.buscarSemanticoIa.mockResolvedValue(RESPUESTA);
    api.registrarFeedbackBusquedaIa.mockResolvedValue({});
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'políticas');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => screen.getByTestId('ia-bs-resultados'));
    await user.click(screen.getAllByTestId('ia-bs-vote-up')[0]);
    await waitFor(() => expect(api.registrarFeedbackBusquedaIa).toHaveBeenCalled());
  });

  it('feedback negativo', async () => {
    api.buscarSemanticoIa.mockResolvedValue(RESPUESTA);
    api.registrarFeedbackBusquedaIa.mockResolvedValue({});
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'políticas');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => screen.getByTestId('ia-bs-resultados'));
    await user.click(screen.getAllByTestId('ia-bs-vote-down')[0]);
    await waitFor(() => expect(api.registrarFeedbackBusquedaIa).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ util: false }),
    ));
  });

  it('feedback con error revierte estado', async () => {
    api.buscarSemanticoIa.mockResolvedValue(RESPUESTA);
    api.registrarFeedbackBusquedaIa.mockRejectedValue(new Error('e'));
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'políticas');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => screen.getByTestId('ia-bs-resultados'));
    await user.click(screen.getAllByTestId('ia-bs-vote-up')[0]);
    // Botón vuelve a habilitar (try again).
    await waitFor(() => expect(screen.getAllByTestId('ia-bs-vote-up')[0]).not.toBeDisabled());
  });

  it('error de búsqueda', async () => {
    api.buscarSemanticoIa.mockRejectedValue(new Error('falló búsqueda'));
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'x');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => expect(screen.getByTestId('ia-bs-error').textContent).toMatch(/falló/));
  });

  it('error budget muestra mensaje específico', async () => {
    const err = Object.assign(new Error('over'), { code: 'ia_budget_exceeded' });
    api.buscarSemanticoIa.mockRejectedValue(err);
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'x');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => expect(screen.getByTestId('ia-bs-error').textContent).toMatch(/Presupuesto/));
  });

  it('sin resultados muestra empty', async () => {
    api.buscarSemanticoIa.mockResolvedValue({ resultados: [] });
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    await user.type(screen.getByTestId('ia-bs-query'), 'inexistente');
    await user.click(screen.getByTestId('ia-bs-submit'));
    await waitFor(() => expect(screen.getByTestId('ia-bs-empty')).toBeInTheDocument());
  });

  it('submit con query vacía no llama API', async () => {
    const user = userEvent.setup();
    render(<BusquedaSemantica session={{ token: 't' }} roles={['gd.profesional']} />);
    expect(screen.getByTestId('ia-bs-submit')).toBeDisabled();
    // forzar submit por enter en form vacío.
    await user.click(screen.getByTestId('ia-bs-query'));
    expect(api.buscarSemanticoIa).not.toHaveBeenCalled();
  });
});
