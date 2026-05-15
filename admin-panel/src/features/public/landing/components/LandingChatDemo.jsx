import styles from './LandingChatDemo.module.css';

/**
 * UI-016.4 — Demo card del hero. Renderiza una conversación de muestra
 * (cliente ↔ asistente) idéntica al HTML del diseñador, más dos estadísticas
 * de impacto (1ª respuesta, conversión).
 *
 * Source-of-truth visual: `docs/HTML DESIGN/Transversales/L1 _ Home _ Landing comercial.html`.
 */
export function LandingChatDemo() {
  return (
    <div className={styles.demoCard} aria-label="Demostración de conversación">
      <header className={styles.demoHeader}>
        <div className={styles.demoAvatar} aria-hidden="true">
          SD
        </div>
        <div className={styles.demoHeaderText}>
          <span className={styles.demoTitle}>Asistente · Sonríe Dental</span>
          <span className={styles.demoStatus}>
            <span className={styles.demoStatusDot} aria-hidden="true" />
            En línea · responde en &lt; 60s
          </span>
        </div>
      </header>

      <div className={styles.demoChat} role="log" aria-label="Conversación de ejemplo">
        <div className={`${styles.bubble} ${styles.bubbleUser}`}>
          Hola, ¿tienen disponibilidad para limpieza dental esta semana?
        </div>
        <div className={`${styles.bubble} ${styles.bubbleBot}`}>
          ¡Hola! 👋 Sí, tengo cupos con el Dr. García:
          <br />• Mañana 10am · Chapinero
          <br />• Jueves 4pm · Usaquén
          <br />
          <br />¿Cuál te queda mejor?
        </div>
        <div className={`${styles.bubble} ${styles.bubbleUser}`}>Mañana 10am 🙏</div>
        <div className={styles.bubbleConfirmation}>
          <div className={styles.bubbleConfirmationTitle}>✅ Cita confirmada</div>
          <div>
            15/05 · 10:00 · Limpieza dental · Dr. García · Sede Chapinero. Te enviaré recordatorio el día anterior.
          </div>
        </div>
        <p className={styles.demoFootnote}>responde tu cliente · 14 may · 09:42</p>
      </div>

      <div className={styles.demoStats}>
        <div className={styles.demoStat}>
          <span className={styles.demoStatLabel}>1ª respuesta</span>
          <span className={styles.demoStatValue}>48s</span>
          <span className={styles.demoStatDelta}>vs. 4h 12min sin bot</span>
        </div>
        <div className={styles.demoStat}>
          <span className={styles.demoStatLabel}>Conversión</span>
          <span className={styles.demoStatValue}>68%</span>
          <span className={`${styles.demoStatDelta} ${styles.demoStatDeltaUp}`}>
            ▲ 6 pts esta semana
          </span>
        </div>
      </div>
    </div>
  );
}
