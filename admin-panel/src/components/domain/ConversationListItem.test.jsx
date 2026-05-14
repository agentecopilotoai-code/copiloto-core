import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ConversationListItem } from './ConversationListItem.jsx';

describe('ConversationListItem', () => {
  it('renders title, status, preview and tags', () => {
    render(
      <ConversationListItem
        title="Ana López"
        statusText="Abierta"
        preview="Hola, quiero una cita"
        tags={[{ id: 't1', name: 'VIP' }]}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('Ana López')).toBeInTheDocument();
    expect(screen.getByText('Abierta')).toBeInTheDocument();
    expect(screen.getByText('Hola, quiero una cita')).toBeInTheDocument();
    expect(screen.getByText('VIP')).toBeInTheDocument();
  });

  it('renders the badges slot', () => {
    render(
      <ConversationListItem
        title="Ana"
        badges={<span>🚨 Urgente</span>}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByText('🚨 Urgente')).toBeInTheDocument();
  });

  it('calls onSelect when clicked', async () => {
    const onSelect = vi.fn();
    render(<ConversationListItem title="Ana" onSelect={onSelect} />);
    await userEvent.click(screen.getByRole('button'));
    expect(onSelect).toHaveBeenCalledOnce();
  });
});
