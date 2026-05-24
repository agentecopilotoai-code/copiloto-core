import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  subirArchivo: vi.fn(),
  registrarFirmaEscaneada: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { FirmaEscaneadaModal } from './FirmaEscaneadaModal.jsx';

// JSDOM FileReader returns null for the result; stub it deterministically.
beforeEach(() => {
  globalThis.FileReader = class {
    constructor() { this.onload = null; this.onerror = null; }
    readAsDataURL() {
      this.result = 'data:image/png;base64,QUJD';
      setTimeout(() => this.onload && this.onload({ target: { result: this.result } }), 0);
    }
  };
});

function makeImage(name = 'firma.png', type = 'image/png', size = 1024) {
  const f = new File(['x'], name, { type });
  Object.defineProperty(f, 'size', { value: size });
  return f;
}

describe('FirmaEscaneadaModal', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza modal', () => {
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} />);
    expect(screen.getByTestId('firma-escaneada-modal')).toBeInTheDocument();
  });

  it('rechaza tipo no imagen', () => {
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('firma-escaneada-file'), {
      target: { files: [makeImage('a.pdf', 'application/pdf')] },
    });
    expect(screen.getByTestId('firma-escaneada-fileerr').textContent).toMatch(/Formato/);
  });

  it('rechaza tamaño > 2MB', () => {
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('firma-escaneada-file'), {
      target: { files: [makeImage('big.png', 'image/png', 3 * 1024 * 1024)] },
    });
    expect(screen.getByTestId('firma-escaneada-fileerr').textContent).toMatch(/2 MB/);
  });

  it('acepta imagen válida', () => {
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('firma-escaneada-file'), {
      target: { files: [makeImage()] },
    });
    expect(screen.getByTestId('firma-escaneada-filename')).toBeInTheDocument();
  });

  it('submit OK invoca subir + registrar', async () => {
    api.subirArchivo.mockResolvedValue({ id: 'a1' });
    api.registrarFirmaEscaneada.mockResolvedValue({ ok: true });
    const onSuccess = vi.fn();
    const user = userEvent.setup();
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} onSuccess={onSuccess} />);
    fireEvent.change(screen.getByTestId('firma-escaneada-file'), {
      target: { files: [makeImage()] },
    });
    fireEvent.change(screen.getByLabelText(/Observación/i), { target: { value: 'firma manuscrita escaneada' } });
    await user.click(screen.getByTestId('firma-escaneada-submit'));
    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(api.subirArchivo).toHaveBeenCalled();
    expect(api.registrarFirmaEscaneada).toHaveBeenCalled();
  });

  it('submit error muestra alert', async () => {
    api.subirArchivo.mockRejectedValue(new Error('boom'));
    const user = userEvent.setup();
    render(<FirmaEscaneadaModal session={{ token: 't' }} documentoId="d1" onClose={() => {}} />);
    fireEvent.change(screen.getByTestId('firma-escaneada-file'), {
      target: { files: [makeImage()] },
    });
    fireEvent.change(screen.getByLabelText(/Observación/i), { target: { value: 'observación válida 1' } });
    await user.click(screen.getByTestId('firma-escaneada-submit'));
    // FileReader async + subir error
    await waitFor(() => expect(api.subirArchivo).toHaveBeenCalled());
  });
});
