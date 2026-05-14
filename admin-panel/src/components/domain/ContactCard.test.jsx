import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ContactCard } from './ContactCard.jsx';

const contact = {
  id: 'c1',
  display_name: 'Ana López',
  phone_e164: '+573001234567',
  appointments_count: 3,
  tags: [{ id: 't1', name: 'VIP' }],
};

describe('ContactCard', () => {
  it('renders the contact name, phone and appointment count', () => {
    render(<ContactCard contact={contact} onSelect={() => {}} />);
    expect(screen.getByText('Ana López')).toBeInTheDocument();
    expect(screen.getByText('+573001234567')).toBeInTheDocument();
    expect(screen.getByText('3 citas')).toBeInTheDocument();
    expect(screen.getByText('VIP')).toBeInTheDocument();
  });

  it('reflects the selected state via aria-pressed', () => {
    render(<ContactCard contact={contact} selected onSelect={() => {}} />);
    expect(screen.getByRole('button')).toHaveAttribute('aria-pressed', 'true');
  });

  it('calls onSelect when clicked', async () => {
    const onSelect = vi.fn();
    render(<ContactCard contact={contact} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledOnce();
  });
});
