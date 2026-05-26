import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../../../services/coreApi.js', () => ({
  createTenantAsPlatformOwner: vi.fn(),
}));

// eslint-disable-next-line no-unused-vars
import { createTenantAsPlatformOwner } from '../../../../services/coreApi.js';
import { CreateTenantModal } from './CreateTenantModal.jsx';

const SESSION = { accessToken: 'tk' };

beforeEach(() => {
  createTenantAsPlatformOwner.mockReset();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe('<CreateTenantModal/>', () => {
  it('no renderiza nada cuando open=false', () => {
    const { container } = render(
      <CreateTenantModal session={SESSION} open={false} onClose={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renderiza el form cuando open=true', () => {
    render(<CreateTenantModal session={SESSION} open onClose={() => {}} />);
    expect(screen.getByTestId('create-tenant-display-name')).toBeInTheDocument();
    expect(screen.getByTestId('create-tenant-submit')).toBeDisabled();
  });

  it('crea el tenant y dispara onCreated + onClose', async () => {
    createTenantAsPlatformOwner.mockResolvedValue({ id: 't1', slug: 'acme' });
    const onCreated = vi.fn();
    const onClose = vi.fn();
    render(
      <CreateTenantModal
        session={SESSION}
        open
        onClose={onClose}
        onCreated={onCreated}
      />,
    );
    await userEvent.type(screen.getByTestId('create-tenant-display-name'), 'Acme');
    await userEvent.click(screen.getByTestId('create-tenant-submit'));
    await waitFor(() => {
      expect(createTenantAsPlatformOwner).toHaveBeenCalledWith(
        SESSION,
        expect.objectContaining({ display_name: 'Acme', slug: 'acme' }),
      );
    });
    expect(onCreated).toHaveBeenCalledWith({ id: 't1', slug: 'acme' });
    expect(onClose).toHaveBeenCalled();
  });

  it('muestra error cuando el backend falla', async () => {
    createTenantAsPlatformOwner.mockRejectedValue(new Error('slug ocupado'));
    render(
      <CreateTenantModal session={SESSION} open onClose={() => {}} onCreated={() => {}} />,
    );
    await userEvent.type(screen.getByTestId('create-tenant-display-name'), 'Acme');
    await userEvent.click(screen.getByTestId('create-tenant-submit'));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('slug ocupado');
    });
  });

  it('botón Cancelar dispara onClose', async () => {
    const onClose = vi.fn();
    render(<CreateTenantModal session={SESSION} open onClose={onClose} />);
    await userEvent.click(screen.getByRole('button', { name: 'Cancelar' }));
    expect(onClose).toHaveBeenCalled();
  });

  it('permite cambiar país y vertical', async () => {
    render(<CreateTenantModal session={SESSION} open onClose={() => {}} />);
    const selects = screen.getAllByRole('combobox');
    await userEvent.selectOptions(selects[0], 'MX');
    expect(selects[0].value).toBe('MX');
  });

  it('respeta slug manual sobre slug auto', async () => {
    createTenantAsPlatformOwner.mockResolvedValue({ id: 't1', slug: 'custom-slug' });
    const onCreated = vi.fn();
    render(
      <CreateTenantModal session={SESSION} open onClose={() => {}} onCreated={onCreated} />,
    );
    await userEvent.type(screen.getByTestId('create-tenant-display-name'), 'Acme');
    await userEvent.type(screen.getByTestId('create-tenant-slug'), 'custom-slug');
    await userEvent.click(screen.getByTestId('create-tenant-submit'));
    await waitFor(() => {
      expect(createTenantAsPlatformOwner).toHaveBeenCalledWith(
        SESSION,
        expect.objectContaining({ slug: 'custom-slug' }),
      );
    });
  });
});
