import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  listDocumentos: vi.fn(),
  subirArchivo: vi.fn(),
  crearDocumento: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { CargarDocumentoModal } from './CargarDocumentoModal.jsx';

function makeFile(name = 'doc.pdf', type = 'application/pdf', size = 1024) {
  const f = new File(['x'.repeat(size)], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

describe('CargarDocumentoModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza dropzone + form', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    expect(screen.getByTestId('cargar-doc-modal')).toBeInTheDocument();
    expect(screen.getByTestId('cargar-dropzone')).toBeInTheDocument();
  });

  it('rechaza extensión no permitida', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    const input = screen.getByTestId('cargar-file-input');
    fireEvent.change(input, { target: { files: [makeFile('virus.exe', 'application/octet-stream')] } });
    expect(screen.getByRole('alert').textContent).toMatch(/Formato/);
  });

  it('rechaza tamaño > 50MB', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    const input = screen.getByTestId('cargar-file-input');
    fireEvent.change(input, { target: { files: [makeFile('big.pdf', 'application/pdf', 60 * 1024 * 1024)] } });
    expect(screen.getByRole('alert').textContent).toMatch(/tamaño/);
  });

  it('acepta archivo válido y autocompleta título', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('cargar-file-input'), {
      target: { files: [makeFile('Reporte Anual.pdf')] },
    });
    expect(screen.getByTestId('archivo-seleccionado')).toBeInTheDocument();
    expect(screen.getByTestId('cargar-titulo').value).toBe('Reporte Anual');
  });

  it('quitar resetea archivo', async () => {
    const user = userEvent.setup();
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('cargar-file-input'), {
      target: { files: [makeFile()] },
    });
    await user.click(screen.getByTestId('cargar-quitar'));
    expect(screen.queryByTestId('archivo-seleccionado')).toBeNull();
  });

  it('submit OK invoca subirArchivo + crearDocumento + onSuccess', async () => {
    api.subirArchivo.mockResolvedValue({ id: 'a1' });
    api.crearDocumento.mockResolvedValue({ id: 'd1' });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByTestId('cargar-file-input'), {
      target: { files: [makeFile()] },
    });
    await user.click(screen.getByTestId('cargar-submit'));
    await waitFor(() => expect(onSuccess).toHaveBeenCalledWith({ id: 'd1' }));
    expect(api.subirArchivo).toHaveBeenCalled();
    expect(api.crearDocumento).toHaveBeenCalled();
  });

  it('submit error muestra alert', async () => {
    api.subirArchivo.mockRejectedValueOnce(new Error('boom'));
    const user = userEvent.setup();
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('cargar-file-input'), {
      target: { files: [makeFile()] },
    });
    await user.click(screen.getByTestId('cargar-submit'));
    await waitFor(() => expect(screen.getByRole('alert').textContent).toMatch(/boom/));
  });

  it('drag&drop archivo válido', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    const dz = screen.getByTestId('cargar-dropzone');
    const file = makeFile('drop.pdf');
    fireEvent.drop(dz, { dataTransfer: { files: [file] } });
    expect(screen.getByTestId('archivo-seleccionado')).toBeInTheDocument();
  });

  it('cambio tipo y descripción', () => {
    render(<CargarDocumentoModal session={{ token: 't' }} onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('cargar-tipo'), { target: { value: 'contrato' } });
    fireEvent.change(screen.getByTestId('cargar-desc'), { target: { value: 'obs' } });
    expect(screen.getByTestId('cargar-tipo').value).toBe('contrato');
    expect(screen.getByTestId('cargar-desc').value).toBe('obs');
  });
});
