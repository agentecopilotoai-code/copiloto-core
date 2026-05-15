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

function ToneTrigger({ tone, label }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => toast.push({ tone, title: label, message: `${tone} body` })}
    >
      Trigger-{tone}
    </button>
  );
}

function PushMany({ count }) {
  const toast = useToast();
  return (
    <button
      type="button"
      onClick={() => {
        for (let i = 1; i <= count; i += 1) {
          toast.push({ tone: 'info', title: `Toast ${i}` });
        }
      }}
    >
      Push-{count}
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

  it('renders the four tones with the correct role + data-tone', async () => {
    function Multi() {
      const toast = useToast();
      return (
        <button
          type="button"
          onClick={() => {
            toast.push({ tone: 'success', title: 'S' });
            toast.push({ tone: 'info', title: 'I' });
            toast.push({ tone: 'warn', title: 'W' });
            toast.push({ tone: 'error', title: 'E' });
          }}
        >
          Push-4
        </button>
      );
    }
    render(
      <ToastProvider>
        <Multi />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole('button', { name: 'Push-4' }));
    const success = screen.getByText('S').closest('[data-tone]');
    const info = screen.getByText('I').closest('[data-tone]');
    const warn = screen.getByText('W').closest('[data-tone]');
    const error = screen.getByText('E').closest('[data-tone]');
    expect(success).toHaveAttribute('data-tone', 'success');
    expect(success).toHaveAttribute('role', 'status');
    expect(info).toHaveAttribute('data-tone', 'info');
    expect(info).toHaveAttribute('role', 'status');
    expect(warn).toHaveAttribute('data-tone', 'warn');
    expect(warn).toHaveAttribute('role', 'alert');
    expect(error).toHaveAttribute('data-tone', 'error');
    expect(error).toHaveAttribute('role', 'alert');
  });

  it('auto-dismisses success/info after 4s and warn/error after 8s', async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <ToneTrigger tone="success" label="ok" />
          <ToneTrigger tone="error" label="err" />
        </ToastProvider>,
      );
      act(() => {
        screen.getByRole('button', { name: 'Trigger-success' }).click();
        screen.getByRole('button', { name: 'Trigger-error' }).click();
      });
      expect(screen.getByText('ok')).toBeInTheDocument();
      expect(screen.getByText('err')).toBeInTheDocument();

      // After 4s the success toast disappears, error stays.
      act(() => {
        vi.advanceTimersByTime(4001);
      });
      expect(screen.queryByText('ok')).toBeNull();
      expect(screen.getByText('err')).toBeInTheDocument();

      // After another 4s (total 8s) the error toast also disappears.
      act(() => {
        vi.advanceTimersByTime(4001);
      });
      expect(screen.queryByText('err')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });

  it('limits the visible stack to 5 and queues the rest until a slot opens', async () => {
    vi.useFakeTimers();
    try {
      render(
        <ToastProvider>
          <PushMany count={7} />
        </ToastProvider>,
      );
      act(() => {
        screen.getByRole('button', { name: 'Push-7' }).click();
      });
      // Only 5 should be visible immediately.
      expect(screen.getAllByRole('status').length).toBe(5);
      expect(screen.queryByText('Toast 6')).toBeNull();
      expect(screen.queryByText('Toast 7')).toBeNull();

      // Advance past the 4s auto-close → all 5 visible info toasts close,
      // and the queue drains in FIFO order, surfacing Toast 6 and Toast 7.
      act(() => {
        vi.advanceTimersByTime(4001);
      });
      // Flush microtasks queued by dismiss() for queue promotion.
      act(() => {
        vi.advanceTimersByTime(0);
      });

      // Toast 6 and Toast 7 must now appear (they were queued).
      expect(screen.getByText('Toast 6')).toBeInTheDocument();
      expect(screen.getByText('Toast 7')).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it('explicit timeout overrides the per-tone default', async () => {
    vi.useFakeTimers();
    try {
      function Trig() {
        const toast = useToast();
        return (
          <button
            type="button"
            onClick={() => toast.push({ tone: 'error', title: 'fast', timeout: 50 })}
          >
            T
          </button>
        );
      }
      render(
        <ToastProvider>
          <Trig />
        </ToastProvider>,
      );
      act(() => {
        screen.getByRole('button', { name: 'T' }).click();
      });
      expect(screen.getByText('fast')).toBeInTheDocument();
      act(() => {
        vi.advanceTimersByTime(60);
      });
      expect(screen.queryByText('fast')).toBeNull();
    } finally {
      vi.useRealTimers();
    }
  });
});
