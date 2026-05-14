import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Modal } from './Modal.jsx';

describe('Modal', () => {
  it('does not render when closed', () => {
    render(<Modal open={false} onClose={() => {}} title="Hola">contenido</Modal>);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders title and body when open', () => {
    render(<Modal open onClose={() => {}} title="Confirmar">contenido</Modal>);
    expect(screen.getByRole('dialog', { name: 'Confirmar' })).toBeInTheDocument();
    expect(screen.getByText('contenido')).toBeInTheDocument();
  });

  it('invokes onClose on close button', async () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Hola">x</Modal>);
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar' }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('invokes onClose on Escape', () => {
    const onClose = vi.fn();
    render(<Modal open onClose={onClose} title="Hola">x</Modal>);
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(onClose).toHaveBeenCalled();
  });
});
