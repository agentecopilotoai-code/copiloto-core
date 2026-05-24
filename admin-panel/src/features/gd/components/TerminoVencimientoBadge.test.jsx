import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import {
  TerminoVencimientoBadge,
  computeStatus,
} from './TerminoVencimientoBadge.jsx';

describe('TerminoVencimientoBadge', () => {
  describe('computeStatus (lógica)', () => {
    it('vencido (< 0) → "vencida"', () => {
      expect(computeStatus(-3, 15)).toBe('vencida');
    });
    it('0 días restantes → "danger"', () => {
      expect(computeStatus(0, 15)).toBe('danger');
    });
    it('<=25% del término → "warn"', () => {
      expect(computeStatus(3, 15)).toBe('warn');  // 20%
      expect(computeStatus(15 * 0.25, 15)).toBe('warn');
    });
    it('> 25% del término → "ok"', () => {
      expect(computeStatus(10, 15)).toBe('ok');
    });
    it('sin terminoTotal aplica regla simple <=3 → warn', () => {
      expect(computeStatus(2, 0)).toBe('warn');
      expect(computeStatus(5, null)).toBe('ok');
    });
  });

  it('renderiza dot + texto', () => {
    render(<TerminoVencimientoBadge diasRestantes={5} terminoTotal={15} />);
    expect(screen.getByText('5d')).toBeInTheDocument();
  });

  it('vencido muestra "Vencido Nd"', () => {
    render(<TerminoVencimientoBadge diasRestantes={-2} terminoTotal={15} />);
    expect(screen.getByText('Vencido 2d')).toBeInTheDocument();
  });

  it('compact=true oculta barra', () => {
    const { container } = render(
      <TerminoVencimientoBadge diasRestantes={5} terminoTotal={15} compact />,
    );
    expect(container.querySelector('.vto-bar')).toBeNull();
  });

  it('data-status refleja el estado', () => {
    render(<TerminoVencimientoBadge diasRestantes={1} terminoTotal={15} />);
    expect(screen.getByTestId('vto-badge').getAttribute('data-status')).toBe('warn');
  });

  it('terminoTotal null deshabilita la barra', () => {
    const { container } = render(
      <TerminoVencimientoBadge diasRestantes={5} />,
    );
    expect(container.querySelector('.vto-bar')).toBeNull();
  });
});
