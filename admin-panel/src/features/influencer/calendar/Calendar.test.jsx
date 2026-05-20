import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../permissions/index.js', () => ({
  usePermissions: vi.fn(),
}));

vi.mock('../../../components/ui/index.js', async () => {
  const actual = await vi.importActual('../../../components/ui/index.js');
  return {
    ...actual,
    useConfirm: () => async () => true,  // confirm siempre true en tests
  };
});

import { usePermissions } from '../../../permissions/index.js';
import { Calendar } from './Calendar.jsx';


const PERSONAS = [
  { id: 'p1', name: 'Camila' },
  { id: 'p2', name: 'Valeria' },
];

const POSTS = [
  {
    id: 'post1', persona_id: 'p1', kind: 'photo', status: 'scheduled',
    scheduled_at: '2026-05-19T11:00:00', platforms: ['instagram'], caption: 'hola',
  },
  {
    id: 'post2', persona_id: 'p2', kind: 'reel', status: 'approved',
    scheduled_at: '2026-05-20T15:00:00', platforms: ['tiktok'], caption: 'reel ok',
  },
];


function renderCalendar(props = {}) {
  return render(
    <Calendar
      personas={PERSONAS}
      posts={POSTS}
      currentDate={new Date('2026-05-19T12:00:00')}
      {...props}
    />,
  );
}


describe('<Calendar/> (UI-INFLU-014)', () => {
  it('render con personajes muestra header + filter chips', () => {
    usePermissions.mockReturnValue({ can: () => true });
    renderCalendar();
    expect(screen.getByRole('button', { name: /Camila/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Valeria/i })).toBeInTheDocument();
  });

  it('click en chip filtra los posts del grid', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const user = userEvent.setup();
    renderCalendar();

    // Initial: ambos posts visibles
    expect(screen.getByLabelText(/Post photo a las 11:00/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Post reel a las 15:00/i)).toBeInTheDocument();

    // Click "Camila" para quitarla del filter activo
    await user.click(screen.getByRole('button', { name: /Camila/i }));
    expect(screen.queryByLabelText(/Post photo a las 11:00/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Post reel a las 15:00/i)).toBeInTheDocument();
  });

  it('click en un post abre el drawer con CTAs', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const user = userEvent.setup();
    renderCalendar();
    await user.click(screen.getByLabelText(/Post photo a las 11:00/i));
    expect(screen.getByLabelText('Detalle del post')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Aprobar y publicar/i })).toBeEnabled();
  });

  it('"Aprobar y publicar" disabled sin influencer.posts.approve_publish', async () => {
    usePermissions.mockReturnValue({ can: () => false });
    const user = userEvent.setup();
    renderCalendar();
    await user.click(screen.getByLabelText(/Post photo a las 11:00/i));
    expect(screen.getByRole('button', { name: /Aprobar y publicar/i })).toBeDisabled();
  });

  it('cancelar post dispara onCancel tras confirm', async () => {
    usePermissions.mockReturnValue({ can: () => true });
    const onCancel = vi.fn().mockResolvedValue();
    const user = userEvent.setup();
    renderCalendar({ onCancel });
    await user.click(screen.getByLabelText(/Post photo a las 11:00/i));
    await user.click(screen.getByRole('button', { name: /^Cancelar$/i }));
    expect(onCancel).toHaveBeenCalled();
  });
});
