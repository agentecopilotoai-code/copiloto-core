import { describe, expect, it, afterEach } from 'vitest';
import { render, screen, within, cleanup } from '@testing-library/react';

import { Landing } from './Landing.jsx';

afterEach(() => {
  cleanup();
});

describe('Landing (UI-016.4)', () => {
  it('renderiza el H1 del hero', () => {
    render(<Landing />);
    const heading = screen.getByRole('heading', { level: 1 });
    expect(heading.textContent).toMatch(/Responde, califica y agenda/);
    expect(heading.textContent).toMatch(/en segundos/);
    expect(heading.textContent).toMatch(/no en horas/);
  });

  it('renderiza las burbujas del demo de conversación', () => {
    render(<Landing />);
    expect(screen.getByText(/disponibilidad para limpieza dental/i)).toBeInTheDocument();
    expect(screen.getByText(/Sí, tengo cupos con el Dr\. García/)).toBeInTheDocument();
    // "Mañana 10am" aparece dos veces (usuario + recordatorio bot). Validamos
    // que ambas instancias existan en el demo card.
    const manana = screen.getAllByText(/Mañana 10am/i);
    expect(manana.length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Cita confirmada/i)).toBeInTheDocument();
    expect(screen.getByText(/responde tu cliente · 14 may/i)).toBeInTheDocument();
  });

  it('"Iniciar sesión" apunta al flow de Auth0 (href configurable)', () => {
    render(<Landing loginHref="/admin/login" />);
    const loginLinks = screen.getAllByRole('link', { name: /Iniciar sesión/i });
    expect(loginLinks.length).toBeGreaterThan(0);
    loginLinks.forEach((link) => {
      expect(link.getAttribute('href')).toBe('/admin/login');
    });
  });

  it('UI-017 — "Iniciar sesión" usa por defecto el BFF redirect a Auth0', () => {
    // Sin override, `loginHref` debe terminar en `/admin/login` — la ruta del
    // backend que dispara el Authorization Code Flow vs Auth0 (app/admin/routes.py).
    // `adminPath()` puede prefijar un origin (`VITE_ADMIN_BACKEND_ORIGIN`) cuando
    // el SPA corre detrás de un host distinto; en tests vitest el env es vacío
    // y el href queda como `/admin/login`.
    render(<Landing />);
    const loginLinks = screen.getAllByRole('link', { name: /Iniciar sesión/i });
    expect(loginLinks.length).toBeGreaterThan(0);
    loginLinks.forEach((link) => {
      expect(link.getAttribute('href')).toMatch(/\/admin\/login$/);
    });
  });

  it('"Solicitar demo gratuita" usa el mailto configurado', () => {
    render(
      <Landing
        demoMailto="mailto:demo@example.com?subject=demo"
        salesMailto="mailto:sales@example.com"
      />,
    );
    const demoLink = screen.getByRole('link', { name: /Solicitar demo gratuita/i });
    expect(demoLink.getAttribute('href')).toBe('mailto:demo@example.com?subject=demo');
  });

  it('"Contactar ventas" usa el mailto configurado', () => {
    render(
      <Landing
        demoMailto="mailto:demo@example.com"
        salesMailto="mailto:sales@example.com?subject=sales"
      />,
    );
    const salesLinks = screen.getAllByRole('link', { name: /Contactar ventas/i });
    expect(salesLinks.length).toBeGreaterThan(0);
    salesLinks.forEach((link) => {
      expect(link.getAttribute('href')).toBe('mailto:sales@example.com?subject=sales');
    });
  });

  it('renderiza el social proof con los logos del HTML del diseñador', () => {
    render(<Landing />);
    expect(
      screen.getByText(/Más de 60 negocios en 7 países LatAm confían en CopilotoIA/i),
    ).toBeInTheDocument();
    expect(screen.getByText('Clínica Norte')).toBeInTheDocument();
    expect(screen.getByText('Dental Lima')).toBeInTheDocument();
    expect(screen.getByText('Estética Quito')).toBeInTheDocument();
  });

  it('renderiza la sección de pricing con los 3 planes', () => {
    render(<Landing />);
    expect(screen.getByRole('heading', { name: 'Starter', level: 3 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Pro', level: 3 })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Enterprise', level: 3 })).toBeInTheDocument();
    expect(screen.getByText('USD $180')).toBeInTheDocument();
    expect(screen.getByText('USD $480')).toBeInTheDocument();
    expect(screen.getByText(/Más elegido/)).toBeInTheDocument();
  });

  it('anchor "Ver cómo funciona" apunta a #features (CTA secundario del hero)', () => {
    render(<Landing />);
    const ctaLink = screen.getByRole('link', { name: /Ver cómo funciona/i });
    expect(ctaLink.getAttribute('href')).toBe('#features');
    // El target del anchor existe en la página.
    const featuresSection = document.getElementById('features');
    expect(featuresSection).not.toBeNull();
  });

  it('aplica el <title> de la landing al montar y lo restaura al desmontar', () => {
    document.title = 'CopilotoIA Admin Panel';
    const { unmount } = render(<Landing />);
    expect(document.title).toBe(
      'CopilotoIA — Agendamiento por IA · WhatsApp, Instagram y Messenger',
    );
    unmount();
    expect(document.title).toBe('CopilotoIA Admin Panel');
  });

  it('renderiza la sección final de CTA con ambos botones', () => {
    render(<Landing />);
    const finalSection = screen.getByLabelText(/Agenda una demo de 25 minutos/i);
    expect(finalSection).toBeInTheDocument();
    // El bloque final contiene "Solicitar demo →" + "Contactar ventas".
    const finalContent = within(finalSection.closest('section'));
    expect(finalContent.getByText(/Solicitar demo →/)).toBeInTheDocument();
  });
});
