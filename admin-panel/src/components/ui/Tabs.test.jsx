import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Tabs } from './Tabs.jsx';

const items = [
  { value: 'a', label: 'Alpha', content: <p>contenido A</p> },
  { value: 'b', label: 'Beta', content: <p>contenido B</p> },
];

describe('Tabs', () => {
  it('renders content of default tab', () => {
    render(<Tabs items={items} />);
    expect(screen.getByText('contenido A')).toBeInTheDocument();
    expect(screen.queryByText('contenido B')).not.toBeInTheDocument();
  });

  it('switches tabs on click', async () => {
    render(<Tabs items={items} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(screen.getByText('contenido B')).toBeInTheDocument();
  });

  it('reports change via onChange', async () => {
    const onChange = vi.fn();
    render(<Tabs items={items} onChange={onChange} />);
    await userEvent.click(screen.getByRole('tab', { name: 'Beta' }));
    expect(onChange).toHaveBeenCalledWith('b');
  });
});
