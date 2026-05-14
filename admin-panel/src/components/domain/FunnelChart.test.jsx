import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FunnelChart } from './FunnelChart.jsx';

describe('FunnelChart', () => {
  it('renders a row per segment with its label, percent and count', () => {
    render(
      <FunnelChart
        segments={[
          { label: 'WhatsApp', percent: 56, count: 174 },
          { label: 'Instagram', percent: 22, count: 68 },
        ]}
      />,
    );
    expect(screen.getByText('WhatsApp')).toBeInTheDocument();
    expect(screen.getByText(/56%/)).toBeInTheDocument();
    expect(screen.getByText(/174/)).toBeInTheDocument();
    expect(screen.getByText('Instagram')).toBeInTheDocument();
  });

  it('shows the empty label when there are no segments', () => {
    render(<FunnelChart segments={[]} emptyLabel="Nada que mostrar" />);
    expect(screen.getByText('Nada que mostrar')).toBeInTheDocument();
  });

  it('exposes the aria-label on the list', () => {
    render(
      <FunnelChart
        ariaLabel="Conversión por canal"
        segments={[{ label: 'Web', value: 10 }]}
      />,
    );
    expect(screen.getByLabelText('Conversión por canal')).toBeInTheDocument();
  });
});
