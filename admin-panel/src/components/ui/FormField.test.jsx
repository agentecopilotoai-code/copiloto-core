import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FormField } from './FormField.jsx';

describe('FormField', () => {
  it('associates label with native input', async () => {
    render(<FormField label="Nombre" placeholder="Acme" />);
    const input = screen.getByLabelText('Nombre');
    expect(input).toBeInTheDocument();
    await userEvent.type(input, 'Hola');
    expect(input).toHaveValue('Hola');
  });

  it('shows error and sets aria-invalid', () => {
    render(<FormField label="Email" error="Email inválido" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Email inválido');
    expect(screen.getByLabelText('Email')).toHaveAttribute('aria-invalid', 'true');
  });

  it('shows hint when no error', () => {
    render(<FormField label="Slug" hint="solo a-z" />);
    expect(screen.getByText('solo a-z')).toBeInTheDocument();
  });
});
