import styles from './HandoffBanner.module.css';

const STATES = {
  human_required: { tone: 'warning', icon: '🙋', title: 'Requiere agente humano' },
  waiting_agent: { tone: 'warning', icon: '⏳', title: 'Esperando que un agente la tome' },
  agent_active: { tone: 'accent', icon: '👤', title: 'Conversación tomada por un agente' },
  bot_active: { tone: 'success', icon: '🤖', title: 'Atendida por el bot' },
};

/**
 * HandoffBanner — banner de estado del handoff humano de una conversación.
 *
 * No hace fetch: recibe el estado y el responsable por props.
 *
 * @param {Object} props
 * @param {'human_required'|'waiting_agent'|'agent_active'|'bot_active'|string} props.status
 * @param {string} [props.assignee] Nombre del agente asignado.
 * @param {React.ReactNode} [props.detail] Texto secundario (razón, etc.).
 * @param {React.ReactNode} [props.children] Slot de acciones.
 */
export function HandoffBanner({ status, assignee, detail, children }) {
  const meta = STATES[status] || { tone: 'neutral', icon: 'ℹ️', title: status || 'Estado de handoff' };
  return (
    <div className={[styles.banner, styles[`banner--${meta.tone}`]].join(' ')} role="status">
      <span className={styles.icon} aria-hidden="true">{meta.icon}</span>
      <div className={styles.body}>
        <span className={styles.title}>{meta.title}</span>
        {assignee ? <p className={styles.detail}>Responsable: {assignee}</p> : null}
        {detail ? <p className={styles.detail}>{detail}</p> : null}
        {children}
      </div>
    </div>
  );
}
