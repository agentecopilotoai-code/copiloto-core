import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RadicadoCard } from './RadicadoCard.jsx';

const RAD = {
  id: 'rad-1',
  numero_radicado: '2026-E-000123',
  asunto: 'Solicitud certificado',
  tipo_radicado: 'entrada',
  estado: 'radicado',
  fecha_radicacion: '2026-05-23T10:30:00Z',
  canal_nombre: 'Web',
  dependencia_actual_nombre: 'Talento Humano',
  tercero_iniciales: 'JR',
  dias_restantes: 12,
  termino_dias: 15,
};

describe('RadicadoCard', () => {
  it('renderiza datos básicos', () => {
    render(<RadicadoCard radicado={RAD} />);
    expect(screen.getByText('2026-E-000123')).toBeInTheDocument();
    expect(screen.getByText('Solicitud certificado')).toBeInTheDocument();
    expect(screen.getByText(/Talento Humano/)).toBeInTheDocument();
  });

  it('onClick dispara con el id del radicado', async () => {
    const fn = vi.fn();
    const user = userEvent.setup();
    render(<RadicadoCard radicado={RAD} onClick={fn} />);
    await user.click(screen.getByTestId('radicado-card'));
    expect(fn).toHaveBeenCalledWith('rad-1');
  });

  it('mostrarTercero=true muestra iniciales', () => {
    render(<RadicadoCard radicado={RAD} mostrarTercero />);
    expect(screen.getByText(/JR/)).toBeInTheDocument();
  });

  it('mostrarTercero=false (default) NO muestra iniciales', () => {
    render(<RadicadoCard radicado={RAD} />);
    expect(screen.queryByText(/JR/)).toBeNull();
  });

  it('radicado null → no renderiza', () => {
    const { container } = render(<RadicadoCard radicado={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('estados desconocidos → badge neutral', () => {
    render(<RadicadoCard radicado={{ ...RAD, estado: 'extraño' }} />);
    expect(screen.getByText('extraño')).toBeInTheDocument();
  });

  it('sin dias_restantes no rompe', () => {
    render(<RadicadoCard radicado={{ ...RAD, dias_restantes: undefined }} />);
    expect(screen.getByText('Solicitud certificado')).toBeInTheDocument();
  });

  it('fecha inválida muestra raw', () => {
    render(<RadicadoCard radicado={{ ...RAD, fecha_radicacion: null }} />);
    expect(screen.getByText(/—/)).toBeInTheDocument();
  });
});
