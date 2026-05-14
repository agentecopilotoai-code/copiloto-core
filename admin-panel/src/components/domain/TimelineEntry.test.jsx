import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TimelineEntry } from './TimelineEntry.jsx';

describe('TimelineEntry', () => {
  it('renders title, meta and body', () => {
    render(
      <ul>
        <TimelineEntry title="Nota interna" meta="Equipo · hoy">
          Cliente pidió reagendar
        </TimelineEntry>
      </ul>,
    );
    expect(screen.getByText('Nota interna')).toBeInTheDocument();
    expect(screen.getByText('Equipo · hoy')).toBeInTheDocument();
    expect(screen.getByText('Cliente pidió reagendar')).toBeInTheDocument();
  });

  it('renders as a custom element when "as" is provided', () => {
    const { container } = render(<TimelineEntry as="div" title="X" />);
    expect(container.firstChild.tagName).toBe('DIV');
  });
});
