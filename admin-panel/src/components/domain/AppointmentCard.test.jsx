import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AppointmentCard, appointmentStatusTone } from './AppointmentCard.jsx';

describe('appointmentStatusTone', () => {
  it('maps known statuses', () => {
    expect(appointmentStatusTone('completed')).toBe('success');
    expect(appointmentStatusTone('no_show')).toBe('danger');
    expect(appointmentStatusTone('pending')).toBe('warning');
  });

  it('falls back to neutral for unknown statuses', () => {
    expect(appointmentStatusTone('weird')).toBe('neutral');
  });
});

describe('AppointmentCard', () => {
  const appointment = {
    id: 'a1',
    service_name: 'Limpieza dental',
    status: 'confirmed',
    resource_name: 'Dra. Ruiz',
    payment_status: 'paid',
  };

  it('renders the service, status and resource', () => {
    render(<AppointmentCard appointment={appointment} dateText="14 may 2026" />);
    expect(screen.getByText('Limpieza dental')).toBeInTheDocument();
    expect(screen.getByText('confirmed')).toBeInTheDocument();
    expect(screen.getByText(/Dra\. Ruiz/)).toBeInTheDocument();
  });

  it('shows the payment badge only when showPayment is set', () => {
    const { rerender } = render(<AppointmentCard appointment={appointment} />);
    expect(screen.queryByText('Pagado')).not.toBeInTheDocument();
    rerender(<AppointmentCard appointment={appointment} showPayment />);
    expect(screen.getByText('Pagado')).toBeInTheDocument();
  });
});
