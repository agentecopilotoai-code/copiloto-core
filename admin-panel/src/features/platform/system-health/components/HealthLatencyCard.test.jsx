import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { HealthLatencyCard } from './HealthLatencyCard.jsx';

describe('<HealthLatencyCard/>', () => {
  it('OK message cuando no hay alerta p95', () => {
    render(
      <HealthLatencyCard
        latency={{ p50: 0.5, p95: 2.0, p99: 3.5, count: 100 }}
        alerts={[]}
      />,
    );
    expect(screen.getAllByText(/p50/).length).toBeGreaterThan(0);
    expect(screen.getByText(/Dentro del objetivo/)).toBeInTheDocument();
    expect(screen.getByText('0.50 s')).toBeInTheDocument();
  });

  it('pinta alerta cuando BotResponseLatencyP95High está activa', () => {
    render(
      <HealthLatencyCard
        latency={{ p50: 0.5, p95: 6, p99: 8, count: 50 }}
        alerts={[
          { name: 'BotResponseLatencyP95High', summary: 'p95 sobre 5s' },
        ]}
      />,
    );
    expect(screen.getByText('Alerta')).toBeInTheDocument();
    expect(screen.getByText(/BotResponseLatencyP95High/)).toBeInTheDocument();
  });

  it('latency null pinta — y count=0', () => {
    render(<HealthLatencyCard latency={null} alerts={null} />);
    expect(screen.getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.getByText(/0 respuestas observadas/)).toBeInTheDocument();
  });
});
