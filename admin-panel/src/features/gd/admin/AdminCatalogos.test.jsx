import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listCatalogos: vi.fn(),
  listItemsCatalogo: vi.fn(),
  crearItemCatalogo: vi.fn(),
  actualizarItemCatalogo: vi.fn(),
  inactivarItemCatalogo: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { AdminCatalogos } from './AdminCatalogos.jsx';

const ROLES = ['gd.admin_sistema'];
const CAT = { codigo: 'canales', nombre: 'Canales de radicación', total: 2 };
const ITEM = { id: 'c1', codigo: 'web', nombre: 'Portal web', activo: true };

describe('AdminCatalogos', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.listCatalogos.mockResolvedValue([CAT]);
    api.listItemsCatalogo.mockResolvedValue([ITEM]);
  });

  it('layout con lista de catálogos', async () => {
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    expect(screen.getByTestId('cat-layout')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('cat-row')).toBeInTheDocument());
  });

  it('seleccionar muestra ítems', async () => {
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('cat-row'));
    await user.click(screen.getByTestId('cat-row'));
    await waitFor(() => expect(screen.getByTestId('cat-items-table')).toBeInTheDocument());
  });

  it('empty catálogos', async () => {
    api.listCatalogos.mockResolvedValue([]);
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByTestId('cat-empty')).toBeInTheDocument());
  });

  it('error catálogos', async () => {
    api.listCatalogos.mockRejectedValue(new Error('e'));
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('crear ítem submit OK', async () => {
    api.crearItemCatalogo.mockResolvedValue({ id: 'c2' });
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cat-row'));
    await user.click(await screen.findByTestId('cat-item-nuevo'));
    fireEvent.change(screen.getByTestId('cat-item-codigo'), { target: { value: 'email' } });
    fireEvent.change(screen.getByTestId('cat-item-nombre'), { target: { value: 'Correo' } });
    await user.click(screen.getByTestId('cat-item-submit'));
    await waitFor(() => expect(api.crearItemCatalogo).toHaveBeenCalled());
  });

  it('editar ítem pre-llena', async () => {
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cat-row'));
    await user.click(await screen.findByTestId('cat-item-editar'));
    expect(screen.getByTestId('cat-item-nombre').value).toBe('Portal web');
  });

  it('inactivar ítem con motivo', async () => {
    api.inactivarItemCatalogo.mockResolvedValue({ ok: true });
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cat-row'));
    await user.click(await screen.findByTestId('cat-item-inactivar'));
    fireEvent.change(screen.getByLabelText(/Motivo de inactivación/i), { target: { value: 'canal deprecado' } });
    await user.click(screen.getByTestId('cat-item-inactivar-submit'));
    await waitFor(() => expect(api.inactivarItemCatalogo).toHaveBeenCalled());
  });

  it('items empty', async () => {
    api.listItemsCatalogo.mockResolvedValue([]);
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={ROLES} />);
    await user.click(await screen.findByTestId('cat-row'));
    await waitFor(() => expect(screen.getByTestId('cat-items-empty')).toBeInTheDocument());
  });

  it('sin permiso oculta CTAs', async () => {
    const user = userEvent.setup();
    render(<AdminCatalogos session={{ token: 't' }} roles={['gd.usuario_consulta']} />);
    await user.click(await screen.findByTestId('cat-row'));
    await waitFor(() => screen.getByTestId('cat-items-table'));
    expect(screen.queryByTestId('cat-item-nuevo')).toBeNull();
  });
});
