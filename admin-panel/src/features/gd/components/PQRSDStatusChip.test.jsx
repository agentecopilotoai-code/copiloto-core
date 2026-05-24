import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { PQRSDStatusChip } from './PQRSDStatusChip.jsx';

describe('PQRSDStatusChip', () => {
  it.each([
    ['P', 'Petición'],
    ['Q', 'Queja'],
    ['R', 'Reclamo'],
    ['S', 'Sugerencia'],
    ['D', 'Denuncia'],
  ])('renderiza tipo %s con label "%s"', (tipo, label) => {
    render(<PQRSDStatusChip tipo={tipo} />);
    expect(screen.getByText(label)).toBeInTheDocument();
    const chip = screen.getByTestId('pqrsd-status-chip');
    expect(chip.className).toMatch(`tipo-${tipo}`);
  });

  it('acepta minúscula', () => {
    render(<PQRSDStatusChip tipo="p" />);
    expect(screen.getByText('Petición')).toBeInTheDocument();
  });

  it('withLabel=false oculta el texto', () => {
    render(<PQRSDStatusChip tipo="P" withLabel={false} />);
    expect(screen.queryByText('Petición')).not.toBeInTheDocument();
  });

  it('tipo inválido → no renderiza', () => {
    const { container } = render(<PQRSDStatusChip tipo="Z" />);
    expect(container.firstChild).toBeNull();
  });

  it('tipo undefined → no renderiza', () => {
    const { container } = render(<PQRSDStatusChip />);
    expect(container.firstChild).toBeNull();
  });
});
