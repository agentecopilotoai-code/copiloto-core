import shared from '../Landing.module.css';
import styles from './LandingFooter.module.css';

const FOOTER_COLUMNS = [
  {
    heading: 'Producto',
    links: ['Funciones', 'Canales', 'Precios', 'Changelog', 'Roadmap'],
  },
  {
    heading: 'Recursos',
    links: ['Documentación', 'API reference', 'Casos de uso', 'Blog', 'Estado del servicio'],
  },
  {
    heading: 'Empresa',
    links: ['Sobre nosotros', 'Clientes', 'Carreras', 'Prensa', 'Contacto'],
  },
  {
    heading: 'Legal',
    links: ['Términos', 'Privacidad', 'Cookies', 'Cumplimiento', 'Seguridad'],
  },
];

/**
 * UI-016.4 — Footer multicolumna. Como la landing es 100% estática, los links
 * apuntan a `#` (placeholders) — cuando existan páginas reales, se reemplazan.
 */
export function LandingFooter() {
  return (
    <footer className={styles.footer}>
      <div className={shared.container}>
        <div className={styles.footerGrid}>
          <div className={styles.footerBrand}>
            <div className={shared.brand}>
              <span className={shared.brandMark} aria-hidden="true">
                C
              </span>
              <span className={shared.brandName}>CopilotoIA</span>
            </div>
            <p className={styles.footerBody}>
              Agendamiento por IA para negocios de servicios en LatAm. Bogotá · CDMX · Buenos
              Aires · Santiago · Lima.
            </p>
          </div>

          {FOOTER_COLUMNS.map((col) => (
            <nav key={col.heading} className={styles.footerCol} aria-label={col.heading}>
              <span className={styles.footerHeading}>{col.heading}</span>
              {col.links.map((link) => (
                <a key={link} href="#" className={styles.footerLink}>
                  {link}
                </a>
              ))}
            </nav>
          ))}
        </div>

        <div className={styles.footerLegal}>
          <span>© 2026 CopilotoIA SAS · Bogotá, Colombia.</span>
          <span>v2.4 · es-CO · CO MX AR CL PE EC UY</span>
        </div>
      </div>
    </footer>
  );
}
