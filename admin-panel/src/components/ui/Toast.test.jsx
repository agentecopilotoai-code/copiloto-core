import { describe, it, expect, vi } from 'vitest';
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

function ShortTrigger() {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => toast.push({ tone: 'neutral', title: 'AutoToast', message: 'desaparece', timeout: 50 })}
    >
      Trigger-auto
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

  it('auto-dismisses after the configured timeout', async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <ShortTrigger />
        </ToastProvider>,
      );
      // userEvent doesn't play well with fake timers; trigger the click directly.
      act(() => {
        screen.getByRole('button', { name: 'Trigger-auto' }).click();
      });
      expect(screen.getByText('AutoToast')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(60);
      });
      expect(screen.queryByText('AutoToast')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
