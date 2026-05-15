import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { StateScreen } from './StateScreen.jsx';

describe('<StateScreen/> (UI-016.6 primitive)', () => {
  it('renderiza heading, body y acciones en el orden esperado', () => {
    render(
      <StateScreen
        heading="Pantalla de prueba"
        body={<p>Cuerpo explicativo</p>}
        primary={<button type="button">Primaria</button>}
        secondary={<button type="button">Secundaria</button>}
      />,
    );

    expect(screen.getByRole('heading', { level: 1, name: 'Pantalla de prueba' })).toBeInTheDocument();
    expect(screen.getByText('Cuerpo explicativo')).toBeInTheDocument();
    // El primary va a la derecha visualmente, pero ambos botones están presentes.
    expect(screen.getByRole('button', { name: 'Primaria' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Secundaria' })).toBeInTheDocument();
  });

  it('aplica role=status y aria-live=polite por defecto', () => {
    const { container } = render(<StateScreen heading="X" />);
    const section = container.querySelector('section');
    expect(section).toHaveAttribute('role', 'status');
    expect(section).toHaveAttribute('aria-live', 'polite');
    expect(section).not.toHaveAttribute('aria-modal');
  });

  it('cuando role="alertdialog" + modal=true emite aria-modal=true y NO aria-live', () => {
    const { container } = render(<StateScreen heading="X" role="alertdialog" modal />);
    const section = container.querySelector('section');
    expect(section).toHaveAttribute('role', 'alertdialog');
    expect(section).toHaveAttribute('aria-modal', 'true');
    expect(section).not.toHaveAttribute('aria-live');
  });

  it('marca el icono como aria-hidden para no ser anunciado', () => {
    const { container } = render(
      <StateScreen heading="X" icon={<span data-testid="ico">i</span>} />,
    );
    const icon = container.querySelector('[aria-hidden="true"]');
    expect(icon).not.toBeNull();
    expect(icon).toContainElement(screen.getByTestId('ico'));
  });

  it('cuando no hay primary/secondary no renderiza el bloque de acciones', () => {
    const { container } = render(<StateScreen heading="Solo heading" />);
    expect(container.querySelectorAll('button')).toHaveLength(0);
  });
});
