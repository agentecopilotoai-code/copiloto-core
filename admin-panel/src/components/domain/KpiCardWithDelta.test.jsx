import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { KpiCardWithDelta, computeDelta } from './KpiCardWithDelta.jsx';

describe('computeDelta', () => {
  it('returns an up trend when the metric grows', () => {
    const { trend, delta } = computeDelta(120, 100);
    expect(trend).toBe('up');
    expect(delta).toContain('+20.0%');
  });

  it('returns a down trend when the metric falls', () => {
    expect(computeDelta(80, 100).trend).toBe('down');
  });

  it('inverts the trend when invertTrend is set', () => {
    expect(computeDelta(120, 100, true).trend).toBe('down');
  });

  it('returns a flat trend with no delta when previous is missing or zero', () => {
    expect(computeDelta(120, 0)).toEqual({ delta: null, trend: 'flat' });
    expect(computeDelta(120, undefined)).toEqual({ delta: null, trend: 'flat' });
  });
});

describe('KpiCardWithDelta', () => {
  it('renders the label, value and computed delta', () => {
    render(<KpiCardWithDelta label="MRR" value="$1.200" current={1200} previous={1000} />);
    expect(screen.getByText('MRR')).toBeInTheDocument();
    expect(screen.getByText('$1.200')).toBeInTheDocument();
    expect(screen.getByText(/\+20\.0%/)).toBeInTheDocument();
  });

  it('omits the delta when there is no previous value', () => {
    render(<KpiCardWithDelta label="MRR" value="$1.200" current={1200} />);
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
  });
});
