import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

import { usePermissions } from '../../../permissions/index.js';
import { Step2Body } from './Step2Body.jsx';


describe('<Step2Body/> (UI-INFLU-009)', () => {
  it('selección de silhouette propaga al payload al avanzar', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const onNext = vi.fn();
    const user = userEvent.setup();
    render(<Step2Body onNext={onNext} />);

    await user.click(screen.getByLabelText(/Slim/i));
    await user.click(screen.getByRole('button', { name: /Siguiente paso/i }));

    expect(onNext).toHaveBeenCalledWith(expect.objectContaining({ silhouette: 'slim' }));
  });

  it('CTA generar vistas disabled sin influencer.generate', () => {
    usePermissions.mockReturnValue({ can: () => false });
    render(<Step2Body />);
    expect(screen.getByRole('button', { name: /Generar vistas/i })).toBeDisabled();
  });

  it('cuando hay bodyViews, NO se muestra el CTA generar', () => {
    usePermissions.mockReturnValue({ can: () => true });
    render(<Step2Body bodyViews={[{ url: 'a' }, { url: 'b' }, { url: 'c' }, { url: 'd' }]} />);
    expect(screen.queryByRole('button', { name: /Generar vistas/i })).not.toBeInTheDocument();
  });
});
