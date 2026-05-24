import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listCorrespondencia: vi.fn(),
  crearBorradorCorrespondenciaExterna: vi.fn(),
}));
import {
  listCorrespondencia,
  crearBorradorCorrespondenciaExterna,
} from '../services/gdApi.js';

import { CorrespondenciaExterna } from './CorrespondenciaExterna.jsx';

const ITEM = {
  id: 'e1', asunto: 'Oficio resp', tercero_destinatario_nombre: 'Juan Q.',
  fecha: '2026-05-23T10:00:00Z', estado: 'borrador',
};

describe('CorrespondenciaExterna', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listCorrespondencia.mockResolvedValue({ items: [ITEM], total: 1 });
  });

  it('renderiza tabs + bandeja borradores por default', async () => {
    render(<CorrespondenciaExterna session={{ token: 't' }} />);
    expect(screen.getByTestId('ce-tabs')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('ce-table')).toBeInTheDocument());
  });

  it('cambio a tab "por-firmar" dispara fetch correcto', async () => {
    const user = userEvent.setup();
    render(<CorrespondenciaExterna session={{ token: 't' }} />);
    await waitFor(() => expect(listCorrespondencia).toHaveBeenCalledTimes(1));
    await user.click(screen.getByTestId('ce-tab-btn-por-firmar'));
    await waitFor(() => expect(listCorrespondencia).toHaveBeenCalledTimes(2));
    const args = listCorrespondencia.mock.calls.at(-1)[1];
    expect(args.bandeja).toBe('por-firmar');
  });

  it('tab Nueva muestra form + submit OK navega a ficha', async () => {
    crearBorradorCorrespondenciaExterna.mockResolvedValueOnce({ id: 'new1' });
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(
      <CorrespondenciaExterna
        session={{ token: 't' }}
        dependencias={[{ id: 'd1', nombre: 'Talento' }]}
        onNavigate={onNavigate}
      />,
    );
    await user.click(screen.getByTestId('ce-tab-btn-nueva'));
    expect(screen.getByTestId('ce-nuevo-form')).toBeInTheDocument();
    fireEvent.change(screen.getByTestId('ce-asunto'), { target: { value: 'Asunto X' } });
    fireEvent.change(screen.getByTestId('ce-dep-origen'), { target: { value: 'd1' } });
    fireEvent.change(screen.getByTestId('ce-destinatario'), { target: { value: 'uuid-tercero' } });
    await user.click(screen.getByTestId('ce-crear-borrador'));
    await waitFor(() => expect(crearBorradorCorrespondenciaExterna).toHaveBeenCalled());
    await waitFor(() => expect(onNavigate).toHaveBeenCalledWith('/gd/correspondencia/new1'));
  });

  it('empty bandeja', async () => {
    listCorrespondencia.mockResolvedValue({ items: [], total: 0 });
    render(<CorrespondenciaExterna session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByTestId('ce-empty')).toBeInTheDocument());
  });

  it('error muestra alert', async () => {
    listCorrespondencia.mockRejectedValue(new Error('e'));
    render(<CorrespondenciaExterna session={{ token: 't' }} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('click en row navega', async () => {
    const onNavigate = vi.fn();
    const user = userEvent.setup();
    render(<CorrespondenciaExterna session={{ token: 't' }} onNavigate={onNavigate} />);
    await waitFor(() => screen.getByTestId('ce-row'));
    await user.click(screen.getByTestId('ce-row'));
    expect(onNavigate).toHaveBeenCalledWith('/gd/correspondencia/e1');
  });
});
