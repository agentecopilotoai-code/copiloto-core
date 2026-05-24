import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { GdTopBar } from './GdTopBar.jsx';

describe('GdTopBar', () => {
  it('renderiza search + scope + notif', () => {
    render(<GdTopBar />);
    expect(screen.getByTestId('gd-search')).toBeInTheDocument();
    expect(screen.getByTestId('gd-scope-selector')).toBeInTheDocument();
    expect(screen.getByTestId('gd-notifications-btn')).toBeInTheDocument();
  });

  it('onSearch dispara cuando el usuario tipea', async () => {
    const fn = vi.fn();
    const user = userEvent.setup();
    render(<GdTopBar onSearch={fn} />);
    await user.type(screen.getByTestId('gd-search'), 'rad');
    expect(fn).toHaveBeenCalled();
  });

  it('onScopeChange dispara al seleccionar otro alcance', () => {
    const fn = vi.fn();
    render(<GdTopBar onScopeChange={fn} />);
    const select = screen.getByLabelText('Cambiar alcance');
    fireEvent.change(select, { target: { value: 'institucional' } });
    expect(fn).toHaveBeenCalledWith('institucional');
  });

  it('unreadNotifications > 0 muestra el dot rojo', () => {
    const { container } = render(<GdTopBar unreadNotifications={3} />);
    expect(container.querySelector('.dot')).toBeTruthy();
  });

  it('user chip renderiza si user', () => {
    render(<GdTopBar user={{ nombre: 'Ana' }} />);
    expect(screen.getByText('Ana')).toBeInTheDocument();
  });

  it('Cmd+K enfoca la búsqueda', () => {
    render(<GdTopBar />);
    const input = screen.getByTestId('gd-search');
    fireEvent.keyDown(window, { key: 'k', metaKey: true });
    expect(document.activeElement).toBe(input);
  });

  it('Ctrl+K también enfoca', () => {
    render(<GdTopBar />);
    const input = screen.getByTestId('gd-search');
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(document.activeElement).toBe(input);
  });
});
