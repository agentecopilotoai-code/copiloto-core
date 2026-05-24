import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { InstitutionalLetterhead } from './InstitutionalLetterhead.jsx';

const ENT = {
  nombre_oficial: 'Alcaldía Municipal de X',
  nit: '900.123.456-7',
  direccion: 'Cra 1 # 2-3',
  telefono: '(601) 123-4567',
  correo_oficial: 'atencion@alcaldia.gov.co',
  sitio_web: 'https://alcaldia.gov.co',
  logo_url: 'https://x/logo.png',
};

describe('InstitutionalLetterhead', () => {
  it('skeleton sin entidad', () => {
    render(<InstitutionalLetterhead />);
    expect(screen.getByTestId('letterhead-skeleton')).toBeInTheDocument();
  });

  it('renderiza nombre + NIT + datos de contacto', () => {
    render(<InstitutionalLetterhead entidad={ENT} />);
    expect(screen.getByText('Alcaldía Municipal de X')).toBeInTheDocument();
    expect(screen.getByText(/900.123.456-7/)).toBeInTheDocument();
    expect(screen.getByText(/Cra 1/)).toBeInTheDocument();
  });

  it('renderiza logo si hay url', () => {
    render(<InstitutionalLetterhead entidad={ENT} />);
    expect(screen.getByAltText(/Logo Alcaldía/)).toBeInTheDocument();
  });

  it('si no hay logo_url, fallback con iniciales', () => {
    const { container } = render(
      <InstitutionalLetterhead entidad={{ ...ENT, logo_url: null }} />,
    );
    expect(container.querySelector('.mark')).toBeTruthy();
    expect(container.querySelector('.mark').textContent).toBe('AL');
  });

  it('subtitle se renderiza si viene', () => {
    render(
      <InstitutionalLetterhead entidad={ENT} subtitle="Constancia de radicación" />,
    );
    expect(screen.getByText('Constancia de radicación')).toBeInTheDocument();
  });
});
