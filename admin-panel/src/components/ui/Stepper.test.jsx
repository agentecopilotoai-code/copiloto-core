import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { Stepper } from './Stepper.jsx';

const STEPS = [
  { key: 'a', label: 'Datos del negocio', status: 'done', description: 'Slug y razón social' },
  { key: 'b', label: 'Canal WhatsApp', status: 'current', description: 'Firma verificada' },
  { key: 'c', label: 'Test E2E', status: 'blocked' },
];

describe('Stepper', () => {
  it('renders every step label and description', () => {
    render(<Stepper steps={STEPS} />);
    expect(screen.getByText('Datos del negocio')).toBeInTheDocument();
    expect(screen.getByText('Canal WhatsApp')).toBeInTheDocument();
    expect(screen.getByText('Test E2E')).toBeInTheDocument();
    expect(screen.getByText('Slug y razón social')).toBeInTheDocument();
  });

  it('marks done steps with a check and pending steps with their index', () => {
    const { container } = render(<Stepper steps={STEPS} />);
    const markers = container.querySelectorAll('ol > li > div > span');
    // first marker (done) shows the check glyph; the current step shows index 2.
    expect(markers[0].textContent).toBe('✓');
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('applies the status class per step', () => {
    const { container } = render(<Stepper steps={STEPS} />);
    const items = container.querySelectorAll('ol > li');
    expect(items[0].className).toMatch(/step--done/);
    expect(items[1].className).toMatch(/step--current/);
    expect(items[2].className).toMatch(/step--blocked/);
  });

  it('renders per-step children and badge slots', () => {
    render(
      <Stepper
        steps={[
          {
            key: 'x',
            label: 'Paso con extras',
            status: 'current',
            badge: <span>BADGE</span>,
            children: <button type="button">Acción</button>,
          },
        ]}
      />,
    );
    expect(screen.getByText('BADGE')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Acción' })).toBeInTheDocument();
  });
});
