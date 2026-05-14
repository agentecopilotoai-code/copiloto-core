import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { HandoffBanner } from './HandoffBanner.jsx';

describe('HandoffBanner', () => {
  it('renders the title for a known status', () => {
    render(<HandoffBanner status="human_required" />);
    expect(screen.getByText('Requiere agente humano')).toBeInTheDocument();
  });

  it('shows the assignee when provided', () => {
    render(<HandoffBanner status="agent_active" assignee="Carla" />);
    expect(screen.getByText('Responsable: Carla')).toBeInTheDocument();
  });

  it('renders children as an actions slot', () => {
    render(
      <HandoffBanner status="bot_active">
        <button type="button">Tomar</button>
      </HandoffBanner>,
    );
    expect(screen.getByRole('button', { name: 'Tomar' })).toBeInTheDocument();
  });
});
