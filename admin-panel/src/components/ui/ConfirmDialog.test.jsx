import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';

import { ConfirmProvider, useConfirm } from './ConfirmDialog.jsx';

function Trigger({ opts, onResult }) {
  const confirm = useConfirm();
  return (
    <button
      type="button"
      onClick={async () => {
        const result = await confirm(opts);
        onResult(result);
      }}
    >
      Disparar
    </button>
  );
}

function Harness({ opts }) {
  const [last, setLast] = useState(null);
  return (
    <ConfirmProvider>
      <Trigger opts={opts} onResult={setLast} />
      <output data-testid="result">{String(last)}</output>
    </ConfirmProvider>
  );
}

describe('ConfirmDialog', () => {
  it('opens the dialog with the provided title/body and resolves true on confirm', async () => {
    render(<Harness opts={{ title: '¿Eliminar?', body: 'Esta acción es permanente.' }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Disparar' }));

    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('¿Eliminar?')).toBeInTheDocument();
    expect(screen.getByText('Esta acción es permanente.')).toBeInTheDocument();

    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Confirmar' }));
    });

    expect(screen.getByTestId('result')).toHaveTextContent('true');
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('resolves false when the user cancels', async () => {
    render(<Harness opts={{ title: '¿Cancelar?' }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Disparar' }));
    await act(async () => {
      await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    });

    expect(screen.getByTestId('result')).toHaveTextContent('false');
  });

  it('uses the danger variant on the confirm button when danger:true', async () => {
    render(<Harness opts={{ title: '¿Borrar todo?', danger: true }} />);

    await userEvent.click(screen.getByRole('button', { name: 'Disparar' }));
    const confirmBtn = await screen.findByRole('button', { name: 'Confirmar' });
    expect(confirmBtn.getAttribute('data-confirm-action')).toBe('confirm');
    // The Button primitive maps variant='danger' to its danger className.
    expect(confirmBtn.className).toMatch(/btn--danger/);
  });
});
