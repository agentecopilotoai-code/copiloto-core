import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TagPill } from './TagPill.jsx';

describe('TagPill', () => {
  it('renders the tag name', () => {
    render(<TagPill tag={{ id: '1', name: 'VIP' }} />);
    expect(screen.getByText('VIP')).toBeInTheDocument();
  });

  it('renders nothing without a tag', () => {
    const { container } = render(<TagPill tag={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('applies the API color via the --tag-color custom property', () => {
    render(<TagPill tag={{ id: '1', name: 'VIP', color: '#ff0000' }} />);
    expect(screen.getByText('VIP').parentElement).toHaveStyle({ '--tag-color': '#ff0000' });
  });

  it('calls onRemove when the remove button is clicked', async () => {
    const onRemove = vi.fn();
    render(<TagPill tag={{ id: '1', name: 'VIP' }} onRemove={onRemove} />);
    await userEvent.click(screen.getByLabelText('Quitar etiqueta VIP'));
    expect(onRemove).toHaveBeenCalledOnce();
  });

  it('hides the remove button when onRemove is not provided', () => {
    render(<TagPill tag={{ id: '1', name: 'VIP' }} />);
    expect(screen.queryByLabelText('Quitar etiqueta VIP')).not.toBeInTheDocument();
  });
});
