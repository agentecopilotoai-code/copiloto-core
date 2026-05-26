import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { RunbookList } from './RunbookList.jsx';

const RUNBOOKS = [
  {
    slug: 'r1',
    title: 'Postgres down',
    category: 'Infraestructura',
    size_bytes: 2048,
    filename: 'r1.md',
  },
];

describe('<RunbookList/>', () => {
  it('empty state cuando no hay runbooks', () => {
    render(<RunbookList runbooks={[]} onSelect={() => {}} />);
    expect(screen.getByText('Sin runbooks')).toBeInTheDocument();
  });

  it('null tolera', () => {
    render(<RunbookList runbooks={null} onSelect={() => {}} />);
    expect(screen.getByText('Sin runbooks')).toBeInTheDocument();
  });

  it('renderiza cada card con título y tamaño', () => {
    render(<RunbookList runbooks={RUNBOOKS} onSelect={() => {}} />);
    expect(screen.getByText('Postgres down')).toBeInTheDocument();
    expect(screen.getByText('2.0 KB')).toBeInTheDocument();
    expect(screen.getByText('r1.md')).toBeInTheDocument();
  });

  it('click dispara onSelect con el slug', async () => {
    const onSelect = vi.fn();
    render(<RunbookList runbooks={RUNBOOKS} onSelect={onSelect} />);
    await userEvent.click(screen.getByText('Postgres down'));
    expect(onSelect).toHaveBeenCalledWith('r1');
  });

  it('Enter / Space en keyboard también dispara onSelect', () => {
    const onSelect = vi.fn();
    render(<RunbookList runbooks={RUNBOOKS} onSelect={onSelect} />);
    const card = screen.getByRole('button');
    card.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true }),
    );
    card.dispatchEvent(
      new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }),
    );
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it('teclas no-Enter/Space no disparan', () => {
    const onSelect = vi.fn();
    render(<RunbookList runbooks={RUNBOOKS} onSelect={onSelect} />);
    const card = screen.getByRole('button');
    card.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'a', bubbles: true, cancelable: true }),
    );
    expect(onSelect).not.toHaveBeenCalled();
  });
});
