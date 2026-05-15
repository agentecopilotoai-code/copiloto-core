import shared from '../Landing.module.css';
import styles from './LandingPricing.module.css';

const PLANS = [
  {
    name: 'Starter',
    price: 'USD $180',
    meta: 'por mes · 1 sede · 2 usuarios',
    description: 'Para negocios que arrancan a digitalizarse',
    features: [
      'WhatsApp + Web widget',
      'Hasta 2,000 conversaciones/mes',
      '1 idioma · 1 país',
      'Soporte por email',
    ],
    cta: 'Empezar prueba →',
    highlight: false,
  },
  {
    name: 'Pro',
    price: 'USD $480',
    meta: 'por mes · hasta 3 sedes · 8 usuarios',
    description: 'El plan que usa el 80% de nuestros clientes',
    features: [
      'Todos los canales (WA + IG + FB + Web)',
      'Conversaciones ilimitadas',
      'Multi-sede + multi-país',
      'Campañas + segmentos + analítica',
      'Onboarding asistido',
      'Soporte prioritario',
    ],
    cta: 'Empezar prueba →',
    highlight: true,
    badge: 'Más elegido',
  },
  {
    name: 'Enterprise',
    price: 'A medida',
    meta: 'sedes y usuarios sin límite',
    description: 'Cadenas, franquicias y operaciones multi-país',
    features: [
      'Dedicated Success Manager',
      'SLA 99.9% contractual',
      'SSO + Auth0 federation',
      'Integración con tu PMS o ERP',
      'Roadmap conjunto',
    ],
    cta: 'Contactar ventas →',
    highlight: false,
    isEnterprise: true,
  },
];

/**
 * UI-016.4 — Pricing teaser. 3 planes (Starter / Pro / Enterprise) con feature
 * checklist. El CTA del Enterprise apunta a `salesMailto`; Starter / Pro apuntan
 * a `demoMailto` (no hay endpoint de signup público todavía).
 *
 * @param {Object} props
 * @param {string} props.demoMailto
 * @param {string} props.salesMailto
 */
export function LandingPricing({ demoMailto, salesMailto }) {
  return (
    <section className={styles.pricing} id="precios" aria-labelledby="landing-pricing-title">
      <div className={shared.container}>
        <div className={shared.sectionHeader}>
          <span className={shared.sectionTag}>Precios</span>
          <h2 id="landing-pricing-title" className={shared.sectionTitle}>
            Sin sorpresas. Cancela cuando quieras.
          </h2>
          <p className={shared.sectionBody}>
            14 días de prueba sin tarjeta. Costo de mensajes WhatsApp se factura aparte por
            Meta.
          </p>
        </div>

        <div className={styles.pricingGrid}>
          {PLANS.map((plan) => {
            const href = plan.isEnterprise ? salesMailto : demoMailto;
            const ctaClass = plan.highlight
              ? `${shared.btnLink} ${shared.btnLinkPrimary} ${styles.planCta}`
              : `${shared.btnLink} ${styles.planCta}`;
            return (
              <article
                key={plan.name}
                className={`${styles.planCard} ${
                  plan.highlight ? styles.planCardHighlight : ''
                }`}
                aria-labelledby={`plan-${plan.name}`}
              >
                {plan.badge ? <span className={styles.planBadge}>{plan.badge}</span> : null}
                <h3 id={`plan-${plan.name}`} className={styles.planName}>
                  {plan.name}
                </h3>
                <div className={styles.planPrice}>{plan.price}</div>
                <div className={styles.planMeta}>{plan.meta}</div>
                <p className={styles.planDescription}>{plan.description}</p>
                <ul className={styles.planFeatures}>
                  {plan.features.map((feature) => (
                    <li key={feature} className={styles.planFeatureItem}>
                      <span className={styles.planCheck} aria-hidden="true">
                        ✓
                      </span>
                      {feature}
                    </li>
                  ))}
                </ul>
                <a href={href} className={ctaClass}>
                  {plan.cta}
                </a>
              </article>
            );
          })}
        </div>
      </div>
    </section>
  );
}
