import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Step1Face } from './Step1Face.jsx';


describe('<Step1Face/> (UI-INFLU-008)', () => {
  it('renderiza el stepper de 5 pasos', () => {
    render(<Step1Face />);
    // 'Cara' aparece en H1 + en Stepper — basta con verificar al menos 1 vez.
    expect(screen.getAllByText('Cara').length).toBeGreaterThan(0);
    expect(screen.getByText('Cuerpo')).toBeInTheDocument();
    expect(screen.getByText('Identidad')).toBeInTheDocument();
    expect(screen.getByText('Voz')).toBeInTheDocument();
    expect(screen.getByText('Plataformas')).toBeInTheDocument();
  });

  it('click en "Aleatorio IA" auto-completa los selectores', async () => {
    const user = userEvent.setup();
    render(<Step1Face />);
    await user.click(screen.getByLabelText(/Aleatorio IA/i));

    // Después del random, "Generar 4 variaciones" debe estar disponible
    // sin AlertBanner de "Faltan campos".
    const generateBtn = screen.getByRole('button', { name: /Generar 4 variaciones/i });
    expect(generateBtn).toBeInTheDocument();
  });

  it('click en "Generar 4 variaciones" llama al callback con payload', async () => {
    const onGenerate = vi.fn().mockResolvedValue({ variations: [] });
    const user = userEvent.setup();
    render(<Step1Face onGenerateVariations={onGenerate} />);
    await user.click(screen.getByLabelText(/Aleatorio IA/i));
    await user.click(screen.getByRole('button', { name: /Generar 4 variaciones/i }));
    expect(onGenerate).toHaveBeenCalled();
    expect(onGenerate.mock.calls[0][0]).toHaveProperty('ethnicity');
    expect(onGenerate.mock.calls[0][0]).toHaveProperty('eye_color');
  });

  it('click en una variación la marca como canonical (aria-pressed)', async () => {
    const user = userEvent.setup();
    render(
      <Step1Face initialVariations={[
        { id: 'v1' }, { id: 'v2' }, { id: 'v3' }, { id: 'v4' },
      ]} />,
    );
    const list = screen.getByLabelText('Variaciones');
    const buttons = within(list).getAllByRole('button');
    await user.click(buttons[1]);
    expect(buttons[1]).toHaveAttribute('aria-pressed', 'true');
    expect(buttons[0]).toHaveAttribute('aria-pressed', 'false');
  });

  it('"Siguiente paso" sin canonical muestra AlertBanner', async () => {
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step1Face onNext={onNext} />);
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));
    expect(onNext).not.toHaveBeenCalled();
    expect(screen.getByText(/Selecciona una variación/i)).toBeInTheDocument();
  });
});
