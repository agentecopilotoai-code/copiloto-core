import shared from '../Landing.module.css';
import styles from './LandingFinalCta.module.css';

/**
 * UI-016.4 — Banner final pre-footer: "Agenda una demo de 25 minutos…" con
 * dos CTAs (Solicitar demo + Contactar ventas).
 *
 * @param {Object} props
 * @param {string} props.demoMailto
 * @param {string} props.salesMailto
 */
export function LandingFinalCta({ demoMailto, salesMailto }) {
  return (
    <section className={styles.finalCta} aria-labelledby="landing-final-cta-title">
      <div className={shared.container}>
        <div className={styles.finalCtaCard}>
          <div>
            <h2 id="landing-final-cta-title" className={styles.finalCtaTitle}>
              Agenda una demo de 25 minutos.
              <br />
              Te mostramos tu propio negocio adentro.
            </h2>
            <p className={styles.finalCtaBody}>
              Sin compromiso. Si te convence, lo dejamos andando en menos de una semana.
            </p>
          </div>
          <div className={styles.finalCtaActions}>
            <a
              href={demoMailto}
              className={`${shared.btnLink} ${shared.btnLinkPrimary} ${shared.btnLinkLg}`}
            >
              Solicitar demo →
            </a>
            <a href={salesMailto} className={`${shared.btnLink} ${shared.btnLinkLg}`}>
              Contactar ventas
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
