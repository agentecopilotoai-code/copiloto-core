import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataTable } from './DataTable.jsx';

const columns = [
  { key: 'name', header: 'Nombre', sortable: true },
  { key: 'mrr', header: 'MRR', align: 'right' },
];

const rows = [
  { id: 'r1', name: 'Acme', mrr: '$1.200' },
  { id: 'r2', name: 'Beta', mrr: '$800' },
];

describe('DataTable', () => {
  it('renders rows and headers', () => {
    render(<DataTable columns={columns} rows={rows} />);
    expect(screen.getByRole('columnheader', { name: /Nombre/ })).toBeInTheDocument();
    expect(screen.getByText('Acme')).toBeInTheDocument();
    expect(screen.getByText('$800')).toBeInTheDocument();
  });

  it('shows empty state when no rows', () => {
    render(<DataTable columns={columns} rows={[]} />);
    expect(screen.getByText('Sin resultados')).toBeInTheDocument();
  });

  it('invokes sort callback', async () => {
    const onSortChange = vi.fn();
    render(<DataTable columns={columns} rows={rows} sort={{ key: 'name', direction: 'asc' }} onSortChange={onSortChange} />);
    await userEvent.click(screen.getByRole('button', { name: /Nombre/ }));
    expect(onSortChange).toHaveBeenCalledWith('name');
  });

  it('fires row click', async () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={columns} rows={rows} onRowClick={onRowClick} />);
    await userEvent.click(screen.getByText('Acme'));
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });
});
