import { LandingChatDemo } from './LandingChatDemo.jsx';
import shared from '../Landing.module.css';
import styles from './LandingHero.module.css';

/**
 * UI-016.4 — Hero section. H1 + body + CTAs primarios + subline de garantías,
 * acompañado a la derecha por la `LandingChatDemo` card.
 *
 * El CTA "Solicitar demo gratuita" usa `mailto:` (no hay endpoint público de
 * lead capture y el HTML del diseñador usa `href="#"` placeholders). "Ver cómo
 * funciona" es un anchor link a la sección de features (`#features`) en la
 * misma página.
 *
 * @param {Object} props
 * @param {string} props.demoMailto — URL `mailto:` para el CTA "Solicitar demo".
 */
export function LandingHero({ demoMailto }) {
  return (
    <section className={styles.hero} aria-labelledby="landing-hero-title">
      <div className={shared.container}>
        <div className={styles.heroGrid}>
          <div>
            <div className={styles.heroPillRow}>
              <span className={styles.pillAccent}>
                <span className={styles.pillDot} aria-hidden="true" />
                Nuevo · Instagram y Facebook Messenger
              </span>
              <span className={styles.pillMuted}>v2.4 · LatAm</span>
            </div>

            <h1 id="landing-hero-title" className={styles.heroTitle}>
              Responde, califica y agenda{' '}
              <span className={styles.heroAccent}>en segundos</span>,
              <br />
              no en horas.
            </h1>

            <p className={styles.heroBody}>
              CopilotoIA conecta tu WhatsApp, Instagram y Messenger con un asistente que
              entiende a tus clientes, agenda citas, manda recordatorios y escala a tu
              equipo cuando hace falta. Sin perder leads. Sin horarios.
            </p>

            <div className={styles.heroCtas}>
              <a
                href={demoMailto}
                className={`${shared.btnLink} ${shared.btnLinkPrimary} ${shared.btnLinkLg}`}
              >
                Solicitar demo gratuita
              </a>
              <a
                href="#features"
                className={`${shared.btnLink} ${shared.btnLinkLg}`}
              >
                Ver cómo funciona →
              </a>
            </div>

            <div className={styles.heroSubline}>
              <span className={styles.heroSublineItem}>
                <span className={styles.heroCheck} aria-hidden="true">
                  ✓
                </span>
                Setup en menos de 30 min
              </span>
              <span className={styles.heroSublineItem}>
                <span className={styles.heroCheck} aria-hidden="true">
                  ✓
                </span>
                Sin tarjeta de crédito
              </span>
              <span className={styles.heroSublineItem}>
                <span className={styles.heroCheck} aria-hidden="true">
                  ✓
                </span>
                Cumple Ley 1581 / GDPR
              </span>
            </div>
          </div>

          <LandingChatDemo />
        </div>
      </div>
    </section>
  );
}
