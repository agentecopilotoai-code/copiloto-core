import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ToastProvider, useToast } from './Toast.jsx';

function Trigger() {
  const toast = useToast();
  return (
    <button type="button" onClick={() => toast.success('Guardado', { title: 'OK' })}>
      Disparar
    </button>
  );
}

describe('Toast', () => {
  it('shows a toast when pushed', async () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Disparar' }));
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.getByText('Guardado')).toBeInTheDocument();
  });

  it('dismisses on close button', async () => {
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Disparar' }));
    const closeBtn = await screen.findByRole('button', { name: 'Cerrar notificación' });
    await act(async () => {
      await userEvent.click(closeBtn);
    });
    expect(screen.queryByText('OK')).not.toBeInTheDocument();
  });
});
