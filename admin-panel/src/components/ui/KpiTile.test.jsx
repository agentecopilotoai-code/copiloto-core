import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KpiTile } from './KpiTile.jsx';

describe('KpiTile', () => {
  it('renders label, value, delta and footnote', () => {
    render(
      <KpiTile
        label="MRR"
        value="$12.4k"
        delta="+8% vs prev 30d"
        trend="up"
        footnote="excluye tax"
      />,
    );
    expect(screen.getByText('MRR')).toBeInTheDocument();
    expect(screen.getByText('$12.4k')).toBeInTheDocument();
    expect(screen.getByText('+8% vs prev 30d')).toBeInTheDocument();
    expect(screen.getByText('excluye tax')).toBeInTheDocument();
  });

  it('applies trend class for down', () => {
    const { container } = render(<KpiTile label="X" value="0" delta="-1%" trend="down" />);
    expect(container.querySelector('[class*="delta--down"]')).not.toBeNull();
  });
});
