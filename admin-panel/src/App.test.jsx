import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// Mock context + router antes del import del SUT.
let mockAuth;
vi.mock('./context/AuthContext.jsx', () => ({
  useAuth: () => mockAuth,
}));

vi.mock('./app/router.jsx', () => ({
  appRouter: { __mock_router__: true, routes: [] },
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    RouterProvider: () => <div data-testid="router-provider">ROUTER</div>,
  };
});

import { App } from './App.jsx';

describe('<App/>', () => {
  it('muestra LoadingScreen mientras la sesión está cargando', () => {
    mockAuth = { isLoading: true };
    render(<App />);
    expect(screen.queryByTestId('router-provider')).toBeNull();
    expect(screen.getByRole('heading', { name: /Cargando sesión/i })).toBeInTheDocument();
  });

  it('monta el RouterProvider cuando la sesión ya se resolvió', () => {
    mockAuth = { isLoading: false };
    render(<App />);
    expect(screen.getByTestId('router-provider')).toBeInTheDocument();
  });
});
