/**
 * Landing pública del Core — pantalla para usuarios no autenticados.
 *
 * Branch `core`: pantalla mínima genérica con CTA de login. Los productos
 * que se instalen sobre el core pueden reemplazar esta pantalla con su
 * propia landing (TODO Fase 3 — module discovery).
 */
import { adminPath } from '../../services/adminSession.js';
import styles from './PublicLanding.module.css';

export function PublicLanding() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <h1 className={styles.title}>Copiloto Core</h1>
        <p className={styles.subtitle}>
          Sistema operativo multi-tenant. Iniciá sesión para acceder al
          panel de administración.
        </p>
        <a
          className={styles.cta}
          href={adminPath('/admin/login')}
          data-testid="public-landing-login"
        >
          Iniciar sesión
        </a>
      </section>
    </main>
  );
}
