import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../services/gdApi.js', () => ({
  enviarCorreoSaliente: vi.fn(),
  listPlantillasCorreo: vi.fn(),
}));
import * as api from '../services/gdApi.js';
import { ComposerCorreoSaliente } from './ComposerCorreoSaliente.jsx';

const ROLES = ['gd.profesional'];

beforeEach(() => {
  vi.clearAllMocks();
  api.listPlantillasCorreo.mockResolvedValue({ items: [
    { id: 'p1', nombre: 'Saludo corporativo', asunto: 'Saludos',
      cuerpo_html: '<p>Cordial saludo</p>' },
  ]});
});

describe('ComposerCorreoSaliente', () => {
  it('sin permiso → aviso', () => {
    render(<ComposerCorreoSaliente session={{}} roles={['gd.usuario_consulta']} />);
    expect(screen.getByTestId('cor-comp-no-perm')).toBeInTheDocument();
  });

  it('envía correo simple', async () => {
    api.enviarCorreoSaliente.mockResolvedValue({ id: 's1' });
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('cor-comp-para'));
    await user.type(screen.getByTestId('cor-comp-para'), 'a@b.com');
    await user.type(screen.getByTestId('cor-comp-asunto'), 'Hola');
    await user.type(screen.getByTestId('cor-comp-cuerpo'), 'Test body');
    await user.click(screen.getByTestId('cor-comp-enviar'));
    await waitFor(() => screen.getByTestId('cor-comp-feedback'));
    expect(api.enviarCorreoSaliente).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        para: ['a@b.com'], asunto: 'Hola', cuerpo_html: 'Test body',
      }),
    );
  });

  it('parsea múltiples destinatarios (coma)', async () => {
    api.enviarCorreoSaliente.mockResolvedValue({ id: 's1' });
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await user.type(screen.getByTestId('cor-comp-para'), 'a@b.com, c@d.com; e@f.com');
    await user.type(screen.getByTestId('cor-comp-asunto'), 'X');
    await user.click(screen.getByTestId('cor-comp-enviar'));
    await waitFor(() => expect(api.enviarCorreoSaliente).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ para: ['a@b.com', 'c@d.com', 'e@f.com'] }),
    ));
  });

  it('aplica plantilla auto-llena cuerpo', async () => {
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await waitFor(() => screen.getByTestId('cor-comp-plantilla'));
    await user.selectOptions(screen.getByTestId('cor-comp-plantilla'), 'p1');
    expect(screen.getByTestId('cor-comp-cuerpo')).toHaveValue('<p>Cordial saludo</p>');
    expect(screen.getByTestId('cor-comp-asunto')).toHaveValue('Saludos');
  });

  it('plantilla con id inexistente no rompe', async () => {
    api.listPlantillasCorreo.mockResolvedValue({ items: [] });
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await user.type(screen.getByTestId('cor-comp-para'), 'x@y.com');
    await user.type(screen.getByTestId('cor-comp-asunto'), 'A');
    expect(screen.getByTestId('cor-comp-enviar')).not.toBeDisabled();
  });

  it('error al enviar', async () => {
    api.enviarCorreoSaliente.mockRejectedValue(new Error('SMTP rechazado'));
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await user.type(screen.getByTestId('cor-comp-para'), 'a@b.com');
    await user.type(screen.getByTestId('cor-comp-asunto'), 'X');
    await user.click(screen.getByTestId('cor-comp-enviar'));
    await waitFor(() => expect(screen.getByTestId('cor-comp-feedback').textContent).toMatch(/SMTP/));
  });

  it('radicado asociado se muestra', async () => {
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES}
      radicadoAsociado="r99" />);
    await waitFor(() => screen.getByTestId('cor-comp-radicado'));
    expect(screen.getByTestId('cor-comp-radicado').textContent).toMatch(/r99/);
  });

  it('preview HTML cuando hay cuerpo', async () => {
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await user.type(screen.getByTestId('cor-comp-cuerpo'), '<p>X</p>');
    // El details está colapsado por defecto pero el element existe.
    expect(screen.getByTestId('cor-comp-preview')).toBeInTheDocument();
  });

  it('cc + bcc se parsean', async () => {
    api.enviarCorreoSaliente.mockResolvedValue({ id: 's1' });
    const user = userEvent.setup();
    render(<ComposerCorreoSaliente session={{ token: 't' }} roles={ROLES} />);
    await user.type(screen.getByTestId('cor-comp-para'), 'a@b.com');
    await user.type(screen.getByTestId('cor-comp-cc'), 'cc@x.com');
    await user.type(screen.getByTestId('cor-comp-bcc'), 'bcc@x.com');
    await user.type(screen.getByTestId('cor-comp-asunto'), 'X');
    await user.click(screen.getByTestId('cor-comp-enviar'));
    await waitFor(() => expect(api.enviarCorreoSaliente).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({
        cc: ['cc@x.com'], bcc: ['bcc@x.com'],
      }),
    ));
  });
});
