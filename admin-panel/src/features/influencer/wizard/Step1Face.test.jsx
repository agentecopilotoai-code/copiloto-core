import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { Step1Face } from './Step1Face.jsx';


describe('<Step1Face/> (UI-INFLU-014.1)', () => {
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
    const onFormChange = vi.fn();
    render(<Step1Face onFormChange={onFormChange} />);
    await user.click(screen.getByLabelText(/Aleatorio IA/i));

    // El callback debe haberse llamado con el form completo de random,
    // con los campos esperados poblados por defaultsForRandom().
    expect(onFormChange).toHaveBeenCalled();
    const lastCallArg = onFormChange.mock.calls.at(-1)[0];
    expect(lastCallArg).toHaveProperty('ethnicity');
    expect(lastCallArg).toHaveProperty('eye_color');
    expect(lastCallArg).toHaveProperty('hair_color');
  });

  it('NO renderiza preview ni variations panel (eso vive en el container)', () => {
    render(<Step1Face />);
    // El refactor 014.1 movió el preview al WizardPreview del container,
    // así que el Step1Face ya no debe tener "VISTA PREVIA" ni "Generar"
    // ni botón "Generar 4 variaciones".
    expect(screen.queryByText(/VISTA PREVIA/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: /Generar 4 variaciones/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Variaciones')).not.toBeInTheDocument();
  });

  it('"Continuar a Cuerpo" llama a onNext SIN bloquear por canonical', async () => {
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step1Face onNext={onNext} />);
    // Antes el wizard exigía "Selecciona una variación como canonical
    // antes de continuar". Ese bloqueo se eliminó — el usuario puede
    // navegar libremente.
    await user.click(screen.getByRole('button', { name: /Continuar a Cuerpo/i }));
    expect(onNext).toHaveBeenCalledOnce();
    // El payload no debe incluir canonical_asset_id (ya no se selecciona aquí).
    const payload = onNext.mock.calls[0][0];
    expect(payload).not.toHaveProperty('canonical_asset_id');
  });

  it('"Guardar borrador" llama a onSaveDraft con el form actual', async () => {
    const onSaveDraft = vi.fn();
    const user = userEvent.setup();
    render(<Step1Face onSaveDraft={onSaveDraft} />);
    await user.click(screen.getByRole('button', { name: /Guardar borrador/i }));
    expect(onSaveDraft).toHaveBeenCalledOnce();
    expect(onSaveDraft.mock.calls[0][0]).toHaveProperty('ethnicity');
  });

  it('onFormChange se llama cuando se cambia algún selector', async () => {
    const onFormChange = vi.fn();
    const user = userEvent.setup();
    render(<Step1Face onFormChange={onFormChange} />);
    // Click en una etnia distinta a la default.
    const ethnicityBtns = screen.getAllByRole('button');
    // Solo click en Aleatorio para asegurar que dispara onFormChange con cambio.
    await user.click(screen.getByLabelText(/Aleatorio IA/i));
    expect(onFormChange).toHaveBeenCalled();
  });
});
