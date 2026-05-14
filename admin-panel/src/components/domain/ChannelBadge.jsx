import { StatusBadge } from '../ui/StatusBadge.jsx';

const CHANNELS = {
  whatsapp: { label: 'WhatsApp', tone: 'success' },
  instagram: { label: 'Instagram', tone: 'accent' },
  messenger: { label: 'Messenger', tone: 'accent' },
  web: { label: 'Widget web', tone: 'neutral' },
  web_widget: { label: 'Widget web', tone: 'neutral' },
};

/**
 * ChannelBadge — indica el canal de un contacto / conversación / lead.
 *
 * @param {Object} props
 * @param {'whatsapp'|'instagram'|'messenger'|'web'|'web_widget'|string} props.channel
 * @param {'solid'|'soft'|'outline'} [props.variant='soft']
 */
export function ChannelBadge({ channel, variant = 'soft' }) {
  const meta = CHANNELS[channel] || { label: channel || '—', tone: 'neutral' };
  return (
    <StatusBadge tone={meta.tone} variant={variant}>
      {meta.label}
    </StatusBadge>
  );
}
