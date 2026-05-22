import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Step1Face } from './Step1Face.jsx';


describe('<Step1Face/> (UI-INFLU-014.2)', () => {
  it('renderiza el stepper de 5 pasos', () => {
    render(<Step1Face />);
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

    // El botón "Generar +1" sigue presente — el flow random no lo bloquea.
    const generateBtn = screen.getByRole('button', { name: /generar nueva variación/i });
    expect(generateBtn).toBeInTheDocument();
  });

  it('click en "Generar +1" llama al callback con count=1 y payload', async () => {
    const onGenerate = vi.fn().mockResolvedValue({ id: 'req-1' });
    const user = userEvent.setup();
    render(<Step1Face onGenerateVariations={onGenerate} />);
    await user.click(screen.getByLabelText(/Aleatorio IA/i));
    await user.click(screen.getByRole('button', { name: /generar nueva variación/i }));
    expect(onGenerate).toHaveBeenCalled();
    const payload = onGenerate.mock.calls[0][0];
    expect(payload).toHaveProperty('ethnicity');
    expect(payload).toHaveProperty('eye_color');
    // UI-INFLU-014.2: cada click = 1 crédito = 1 variación.
    expect(payload.count).toBe(1);
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

  it('"Siguiente paso" navega libremente sin exigir canonical', async () => {
    // UI-INFLU-014.1: el bloqueo "Selecciona variación canonical antes
    // de continuar" se eliminó. El usuario puede avanzar entre pasos
    // libremente — la selección se exige al activar en step 5.
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step1Face onNext={onNext} />);
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));
    expect(onNext).toHaveBeenCalledOnce();
    // El payload NO debe incluir canonical_asset_id (ya no se exige).
    expect(onNext.mock.calls[0][0]).not.toHaveProperty('canonical_asset_id');
  });

  it('muestra thumbnails con spinner cuando pendingCount > 0', () => {
    render(<Step1Face pendingCount={2} />);
    // Cada pending pinta un role="status" con label "Variación en generación".
    const pending = screen.getAllByRole('status', { name: /Variación en generación/i });
    expect(pending).toHaveLength(2);
  });
});
