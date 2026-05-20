import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

import { PublicLandingShell } from './PublicLandingShell.jsx';


function renderShell(initialPath = '/') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/" element={<PublicLandingShell activeTab="ravit" />} />
        <Route path="/copiloto" element={<PublicLandingShell activeTab="copiloto" />} />
        <Route path="/documentos" element={<PublicLandingShell activeTab="documentos" />} />
      </Routes>
    </MemoryRouter>,
  );
}


describe('<PublicLandingShell/> (3 tabs: Personajes AI / Chatbot AI / Gestión Documental AI)', () => {
  it('/ renderiza shell con tab Personajes AI activo y hero del Pulse', () => {
    renderShell('/');
    expect(screen.getByTestId('public-landing-shell')).toBeInTheDocument();
    expect(screen.getByTestId('ravit-agent-pulse')).toBeInTheDocument();
    // Hero del rediseño: h1 "Tu marca, con cara propia.".
    const h1 = screen.getByRole('heading', { level: 1 });
    expect(h1).toHaveTextContent(/Tu marca/i);
    expect(h1).toHaveTextContent(/cara propia/i);
    const ravitTab = screen.getByRole('link', { name: 'Personajes AI' });
    expect(ravitTab).toHaveAttribute('aria-current', 'page');
  });

  it('/copiloto renderiza shell con tab Chatbot AI activo y monta Landing embedded', () => {
    renderShell('/copiloto');
    expect(screen.getByTestId('public-landing')).toBeInTheDocument();
    expect(screen.queryByTestId('ravit-agent-pulse')).not.toBeInTheDocument();
    expect(screen.queryByTestId('documents-landing')).not.toBeInTheDocument();
    const copTab = screen.getByRole('link', { name: 'Chatbot AI' });
    expect(copTab).toHaveAttribute('aria-current', 'page');
  });

  it('/documentos renderiza shell con tab Gestión Documental AI activo y monta DocumentsLanding', () => {
    renderShell('/documentos');
    expect(screen.getByTestId('documents-landing')).toBeInTheDocument();
    expect(screen.queryByTestId('ravit-agent-pulse')).not.toBeInTheDocument();
    expect(screen.queryByTestId('public-landing')).not.toBeInTheDocument();
    const docTab = screen.getByRole('link', { name: 'Gestión Documental AI' });
    expect(docTab).toHaveAttribute('aria-current', 'page');
  });

  it('CTA "Empezar gratis" abre modal con form + submit dispara onDemoRequest', async () => {
    const onDemoRequest = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<PublicLandingShell activeTab="ravit" onDemoRequest={onDemoRequest} />} />
        </Routes>
      </MemoryRouter>,
    );
    const buttons = screen.getAllByRole('button', { name: /Empezar gratis/i });
    await user.click(buttons[0]);
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    await user.type(screen.getByLabelText(/Nombre/i), 'Sofia');
    await user.type(screen.getByLabelText(/Email/i), 'sofia@example.com');
    await user.click(screen.getByRole('button', { name: 'Enviar' }));
    expect(onDemoRequest).toHaveBeenCalledOnce();
    expect(onDemoRequest.mock.calls[0][0]).toMatchObject({ name: 'Sofia', email: 'sofia@example.com' });
  });

  it('CTA "Iniciar sesión" usa loginHref como destino', () => {
    render(
      <MemoryRouter>
        <PublicLandingShell activeTab="ravit" loginHref="/login-test" />
      </MemoryRouter>,
    );
    const loginLinks = screen.getAllByRole('link', { name: /Iniciar sesión/i });
    expect(loginLinks[0]).toHaveAttribute('href', '/login-test');
  });

  it('los 3 tabs son visibles en cualquier pestaña', () => {
    renderShell('/copiloto');
    expect(screen.getByRole('link', { name: 'Personajes AI' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Chatbot AI' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Gestión Documental AI' })).toBeInTheDocument();
  });
});
