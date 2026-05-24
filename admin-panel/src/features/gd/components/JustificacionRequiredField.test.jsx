import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { JustificacionRequiredField } from './JustificacionRequiredField.jsx';

function Wrapper({ initial = '', ...props }) {
  const [v, setV] = React.useState(initial);
  return (
    <JustificacionRequiredField
      value={v}
      onChange={(next, valid) => {
        setV(next);
        props.onChange?.(next, valid);
      }}
      {...props}
    />
  );
}

// Need React in scope for Wrapper.
import React from 'react';

describe('JustificacionRequiredField', () => {
  it('renderiza label y asterisco si required', () => {
    render(<Wrapper />);
    expect(screen.getByText(/Justificación/)).toBeInTheDocument();
    expect(screen.getByLabelText(/obligatorio/)).toBeInTheDocument();
  });

  it('no muestra asterisco si required=false', () => {
    render(<Wrapper required={false} />);
    expect(screen.queryByLabelText(/obligatorio/)).toBeNull();
  });

  it('onChange recibe value + isValid', () => {
    const fn = vi.fn();
    const { rerender } = render(
      <JustificacionRequiredField value="" onChange={fn} />,
    );
    // Simular el flujo controlado con value cambiando.
    rerender(<JustificacionRequiredField value="short" onChange={fn} />);
    rerender(
      <JustificacionRequiredField
        value="texto largo válido"
        onChange={fn}
      />,
    );
    // Probar handleChange directamente vía fireEvent.
    const ta = screen.getByTestId('justificacion-required-field');
    fireEvent.change(ta, { target: { value: 'ya largo enough' } });
    expect(fn).toHaveBeenLastCalledWith('ya largo enough', true);

    fireEvent.change(ta, { target: { value: 'noo' } });
    expect(fn).toHaveBeenLastCalledWith('noo', false);
  });

  it('muestra error tras blur si inválido', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);
    const ta = screen.getByTestId('justificacion-required-field');
    await user.type(ta, 'corto');
    await user.tab();
    expect(screen.getByText(/Mínimo 10 caracteres/)).toBeInTheDocument();
  });

  it('respeta maxLength truncando input', () => {
    const fn = vi.fn();
    render(
      <JustificacionRequiredField value="" onChange={fn} maxLength={5} />,
    );
    fireEvent.change(screen.getByTestId('justificacion-required-field'), {
      target: { value: 'abcdefghij' },
    });
    expect(fn).toHaveBeenLastCalledWith('abcde', expect.any(Boolean));
  });

  it('contador refleja chars', async () => {
    const user = userEvent.setup();
    render(<Wrapper />);
    await user.type(screen.getByTestId('justificacion-required-field'), 'hola');
    expect(screen.getByText(/4 \/ 2000/)).toBeInTheDocument();
  });
});
