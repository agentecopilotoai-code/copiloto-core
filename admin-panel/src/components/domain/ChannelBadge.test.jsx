import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChannelBadge } from './ChannelBadge.jsx';

describe('ChannelBadge', () => {
  it('maps a known channel to its label', () => {
    render(<ChannelBadge channel="whatsapp" />);
    expect(screen.getByText('WhatsApp')).toBeInTheDocument();
  });

  it('falls back to the raw value for an unknown channel', () => {
    render(<ChannelBadge channel="telegram" />);
    expect(screen.getByText('telegram')).toBeInTheDocument();
  });
});
