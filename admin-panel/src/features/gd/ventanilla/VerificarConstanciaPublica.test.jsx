import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

import { VerificarConstanciaPublica } from './VerificarConstanciaPublica.jsx';

describe('VerificarConstanciaPublica', () => {
  it('codigo vacío → error inmediato', async () => {
    render(<VerificarConstanciaPublica codigo="" fetchFn={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByTestId('verificar-error')).toBeInTheDocument();
    });
  });

  it('fetch success muestra datos del radicado', async () => {
    const fetchFn = vi.fn().mockResolvedValueOnce({
      numero_radicado: '2026-E-001',
      fecha_radicacion: '2026-05-23T10:00:00Z',
      tipo_radicado: 'entrada',
      estado_actual: 'en_gestion',
      asunto_resumido: 'Solicitud certificado',
      dependencia_actual_publica: 'Talento Humano',
    });
    render(<VerificarConstanciaPublica codigo="AB12CD" fetchFn={fetchFn} />);
    await waitFor(() => {
      expect(screen.getByTestId('verificar-result')).toBeInTheDocument();
    });
    expect(screen.getByText('2026-E-001')).toBeInTheDocument();
    expect(screen.getByText('Solicitud certificado')).toBeInTheDocument();
    expect(screen.getByText('Talento Humano')).toBeInTheDocument();
  });

  it('fetch error muestra alert', async () => {
    const fetchFn = vi.fn().mockRejectedValueOnce(new Error('404'));
    render(<VerificarConstanciaPublica codigo="ZZZ" fetchFn={fetchFn} />);
    await waitFor(() => {
      expect(screen.getByTestId('verificar-error')).toBeInTheDocument();
    });
  });

  it('renderiza entidad cuando viene', async () => {
    const fetchFn = vi.fn().mockResolvedValueOnce({
      numero_radicado: '2026-E-002',
      fecha_radicacion: '2026-05-23T10:00:00Z',
      asunto_resumido: 'X',
    });
    render(
      <VerificarConstanciaPublica
        codigo="X1"
        fetchFn={fetchFn}
        entidad={{ nombre_oficial: 'Alcaldía X', nit: '900-1' }}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/Alcaldía X/)).toBeInTheDocument();
    });
  });
});
