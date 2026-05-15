import shared from '../Landing.module.css';
import styles from './LandingSocialProof.module.css';

const LOGOS = [
  'Clínica Norte',
  'SPA·POLANCO',
  'Dental Lima',
  'vet · santiago',
  'motos/ba',
  'Estética Quito',
  'Bienestar MVD',
];

/**
 * UI-016.4 — Strip de social proof: copy + logos textuales (el HTML del
 * diseñador usa wordmarks, no SVG, para no asumir branding de terceros).
 */
export function LandingSocialProof() {
  return (
    <section
      className={styles.socialProof}
      aria-labelledby="landing-social-proof-label"
      id="clientes"
    >
      <div className={shared.container}>
        <p id="landing-social-proof-label" className={styles.socialProofLabel}>
          Más de 60 negocios en 7 países LatAm confían en CopilotoIA
        </p>
        <div className={styles.socialProofLogos} role="list">
          {LOGOS.map((logo) => (
            <span key={logo} role="listitem" className={styles.socialProofLogo}>
              {logo}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
