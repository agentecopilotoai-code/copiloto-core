import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../services/gdApi.js', () => ({
  getEvidenciaFirma: vi.fn(),
}));
import * as api from '../services/gdApi.js';

import { EvidenciaFirma } from './EvidenciaFirma.jsx';

const EV = {
  documento_titulo: 'Resolución 5',
  firmante_nombre: 'Carmen R.',
  firmante_cargo: 'Secretaria General',
  metodo: 'digital',
  firmado_en: '2026-05-20T10:00:00Z',
  hash_documento: 'sha256-abcdef',
  ip: '10.1.1.1',
  geolocalizacion: { ciudad: 'Bogotá', region: 'Cund.', pais: 'CO' },
  user_agent: 'Chrome 121',
  certificado: {
    emisor: 'AC raíz', serial: '0001',
    valido_desde: '2025-01-01T00:00:00Z',
    valido_hasta: '2027-01-01T00:00:00Z',
    algoritmo: 'SHA-256',
  },
  url_descarga_evidencia: 'https://x/y',
};

describe('EvidenciaFirma', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renderiza evidencia completa', async () => {
    api.getEvidenciaFirma.mockResolvedValue(EV);
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByTestId('evidencia-card')).toBeInTheDocument());
    expect(screen.getByTestId('evidencia-hash').textContent).toMatch(/sha256-abcdef/);
    expect(screen.getByTestId('evidencia-descargar')).toBeInTheDocument();
  });

  it('error', async () => {
    api.getEvidenciaFirma.mockRejectedValue(new Error('e'));
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument());
  });

  it('renderiza sin certificado ni descarga', async () => {
    api.getEvidenciaFirma.mockResolvedValue({
      ...EV, certificado: null, url_descarga_evidencia: null,
    });
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByTestId('evidencia-card')).toBeInTheDocument());
    expect(screen.queryByTestId('evidencia-descargar')).toBeNull();
  });

  it('geo string', async () => {
    api.getEvidenciaFirma.mockResolvedValue({ ...EV, geolocalizacion: 'Cali, CO' });
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByText(/Cali, CO/)).toBeInTheDocument());
  });

  it('geo lat/lon', async () => {
    api.getEvidenciaFirma.mockResolvedValue({
      ...EV, geolocalizacion: { lat: 4.7, lon: -74.1 },
    });
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByText(/4\.7/)).toBeInTheDocument());
  });

  it('método escaneada', async () => {
    api.getEvidenciaFirma.mockResolvedValue({ ...EV, metodo: 'escaneada' });
    render(<EvidenciaFirma session={{ token: 't' }} firmaId="f1" />);
    await waitFor(() => expect(screen.getByText('Firma escaneada')).toBeInTheDocument());
  });
});
