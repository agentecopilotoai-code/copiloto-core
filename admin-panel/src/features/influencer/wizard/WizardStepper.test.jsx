import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';

import { WizardStepper } from './WizardStepper.jsx';

const STEPS = [
  { key: 'face', label: 'Cara', description: 'Rasgos visuales', status: 'done' },
  { key: 'body', label: 'Cuerpo', description: 'Constitución', status: 'done' },
  { key: 'identity', label: 'Identidad', description: 'Nombre y mundo', status: 'current' },
  { key: 'voice', label: 'Voz', description: 'Tono y carácter', status: 'pending' },
  { key: 'platforms', label: 'Plataformas', description: 'Dónde publica', status: 'pending' },
];

describe('<WizardStepper/>', () => {
  it('renders all step labels and descriptions', () => {
    render(<WizardStepper steps={STEPS} />);
    expect(screen.getByText('Cara')).toBeInTheDocument();
    expect(screen.getByText('Rasgos visuales')).toBeInTheDocument();
    expect(screen.getByText('Plataformas')).toBeInTheDocument();
    expect(screen.getByText('Dónde publica')).toBeInTheDocument();
  });

  it('shows check glyph for done steps and numeric index for current/pending', () => {
    const { container } = render(<WizardStepper steps={STEPS} />);
    const markers = container.querySelectorAll('ol > li > div > span[aria-hidden="true"]');
    // First two are done → '✓'
    expect(markers[0].textContent).toBe('✓');
    expect(markers[1].textContent).toBe('✓');
    // Third is current → '3'
    expect(markers[2].textContent).toBe('3');
    // Fourth and fifth pending → '4' and '5'
    expect(markers[3].textContent).toBe('4');
    expect(markers[4].textContent).toBe('5');
  });

  it('marks the current step with aria-current="step"', () => {
    const { container } = render(<WizardStepper steps={STEPS} />);
    const current = container.querySelector('li[aria-current="step"]');
    expect(current).not.toBeNull();
    expect(current.textContent).toContain('Identidad');
  });

  it('applies status modifier classes per step', () => {
    const { container } = render(<WizardStepper steps={STEPS} />);
    const items = container.querySelectorAll('ol > li');
    expect(items[0].className).toMatch(/step--done/);
    expect(items[2].className).toMatch(/step--current/);
    expect(items[3].className).toMatch(/step--pending/);
  });
});
