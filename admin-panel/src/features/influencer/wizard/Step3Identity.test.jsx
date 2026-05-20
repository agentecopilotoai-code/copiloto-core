import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Step3Identity } from './Step3Identity.jsx';


describe('<Step3Identity/> (UI-INFLU-010)', () => {
  it('handle duplicado dispara error inline', async () => {
    const onCheckHandle = vi.fn().mockResolvedValue(true);  // taken
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step3Identity onCheckHandle={onCheckHandle} onNext={onNext} />);
    await user.type(screen.getByLabelText(/Nombre/), 'Sofía');
    await user.type(screen.getByLabelText(/Handle/), 'sofia');
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));
    expect(await screen.findByText(/Handle ya en uso/i)).toBeInTheDocument();
    expect(onNext).not.toHaveBeenCalled();
  });

  it('preview card actualiza al cambiar nombre y city', async () => {
    const user = userEvent.setup();
    render(<Step3Identity />);
    await user.type(screen.getByLabelText(/Nombre/), 'Sofía');
    await user.type(screen.getByLabelText(/Ciudad/), 'Tulum');
    await user.type(screen.getByLabelText(/País/), 'MX');
    const preview = screen.getByLabelText('Preview live');
    expect(preview).toHaveTextContent('Sofía');
    expect(preview).toHaveTextContent('Tulum, MX');
  });

  it('brands chips se agregan y eliminan', async () => {
    const user = userEvent.setup();
    render(<Step3Identity />);
    const input = screen.getByLabelText(/Agregar Brands/);
    await user.type(input, 'Loewe{Enter}');
    expect(screen.getByText('Loewe')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Eliminar Loewe' }));
    expect(screen.queryByText('Loewe')).not.toBeInTheDocument();
  });

  it('siguiente sin nombre → bloqueado con error', async () => {
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step3Identity onNext={onNext} />);
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));
    expect(screen.getByText(/Nombre requerido/i)).toBeInTheDocument();
    expect(onNext).not.toHaveBeenCalled();
  });
});
