import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { RadicadoConstanciaPreview } from './RadicadoConstanciaPreview.jsx';

const RAD = {
  id: 'r1',
  numero_radicado: '2026-E-000123',
  codigo_verificacion: 'AB12CD34',
  fecha_radicacion: '2026-05-23T10:30:00Z',
  tipo_radicado: 'entrada',
  asunto: 'Solicitud certificado laboral',
  canal_nombre: 'Web',
  estado: 'radicado',
};

const ENT = {
  nombre_oficial: 'Alcaldía X',
  nit: '900-1',
};

describe('RadicadoConstanciaPreview', () => {
  it('empty cuando no hay radicado', () => {
    render(<RadicadoConstanciaPreview />);
    expect(screen.getByTestId('constancia-empty')).toBeInTheDocument();
  });

  it('muestra número, código, asunto', () => {
    render(<RadicadoConstanciaPreview radicado={RAD} entidad={ENT} />);
    expect(screen.getByTestId('constancia-preview')).toBeInTheDocument();
    expect(screen.getByText('2026-E-000123')).toBeInTheDocument();
    expect(screen.getByText('Solicitud certificado laboral')).toBeInTheDocument();
    expect(screen.getByTestId('codigo-verificacion').textContent.trim()).toBe('AB12CD34');
  });

  it('QR placeholder presente con aria-label', () => {
    render(<RadicadoConstanciaPreview radicado={RAD} entidad={ENT} />);
    const qr = screen.getByTestId('qr-placeholder');
    expect(qr).toBeInTheDocument();
    expect(qr.getAttribute('aria-label')).toContain('AB12CD34');
  });

  it('fallback código XXXXXXXX cuando falta', () => {
    render(<RadicadoConstanciaPreview radicado={{ ...RAD, codigo_verificacion: null, codigo: null }} entidad={ENT} />);
    expect(screen.getByTestId('codigo-verificacion').textContent.trim()).toBe('XXXXXXXX');
  });

  it('verifyBaseUrl custom se usa en la URL', () => {
    render(
      <RadicadoConstanciaPreview
        radicado={RAD}
        entidad={ENT}
        verifyBaseUrl="https://x.gov.co/v"
      />,
    );
    expect(screen.getByText(/https:\/\/x\.gov\.co\/v\/AB12CD34/)).toBeInTheDocument();
  });
});
