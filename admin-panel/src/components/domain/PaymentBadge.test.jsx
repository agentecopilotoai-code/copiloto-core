import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { PaymentBadge } from './PaymentBadge.jsx';

describe('PaymentBadge', () => {
  it('renders the localized label for a known status', () => {
    render(<PaymentBadge status="paid" />);
    expect(screen.getByText('Pagado')).toBeInTheDocument();
  });

  it('falls back to "Sin pago" when status is missing', () => {
    render(<PaymentBadge status={undefined} />);
    expect(screen.getByText('Sin pago')).toBeInTheDocument();
  });
});
