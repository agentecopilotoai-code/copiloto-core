import { useEffect } from 'react';

import { LandingFeatures } from './components/LandingFeatures.jsx';
import { LandingFinalCta } from './components/LandingFinalCta.jsx';
import { LandingFooter } from './components/LandingFooter.jsx';
import { LandingHeader } from './components/LandingHeader.jsx';
import { LandingHero } from './components/LandingHero.jsx';
import { LandingPricing } from './components/LandingPricing.jsx';
import { LandingSocialProof } from './components/LandingSocialProof.jsx';
import styles from './Landing.module.css';

/**
 * UI-016.4 — Landing comercial pre-login (público).
 *
 * Vista PÚBLICA que se renderiza en `/` cuando NO hay sesión activa. Para
 * usuarios autenticados, el `IndexRedirect` del router (`app/router.jsx`)
 * sigue redirigiendo a la home de su rol; este componente solo se monta para
 * sesiones nulas.
 *
 * Source-of-truth visual: `docs/HTML DESIGN/Transversales/L1 _ Home _ Landing comercial.html`.
 *
 * CTAs:
 *  - "Solicitar demo" / "Solicitar demo gratuita" / "Solicitar demo →" →
 *    `mailto:ventas@copilotoia.com?subject=Solicito demo`.
 *  - "Contactar ventas" → `mailto:ventas@copilotoia.com?subject=Contacto ventas`.
 *  - "Iniciar sesión" → `loginHref` (por defecto `/admin/login`), que dispara
 *    el redirect a Auth0 vía el flujo SPA existente. Cualquier acceso a `/admin`
 *    con sesión válida ya envía a la home del rol; sin sesión, Auth0 toma el
 *    relevo.
 */
const DEFAULT_DEMO_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Solicito%20demo%20CopilotoIA';
const DEFAULT_SALES_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Contacto%20ventas%20CopilotoIA';
const DEFAULT_LOGIN_HREF = '/admin/login';

const LANDING_PAGE_TITLE =
  'CopilotoIA — Agendamiento por IA · WhatsApp, Instagram y Messenger';

export function Landing({
  demoMailto = DEFAULT_DEMO_MAILTO,
  salesMailto = DEFAULT_SALES_MAILTO,
  loginHref = DEFAULT_LOGIN_HREF,
}) {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = LANDING_PAGE_TITLE;
    return () => {
      document.title = previousTitle;
    };
  }, []);

  return (
    <div className={styles.page} data-testid="public-landing">
      <LandingHeader
        loginHref={loginHref}
        demoMailto={demoMailto}
        salesMailto={salesMailto}
      />
      <main>
        <LandingHero demoMailto={demoMailto} />
        <LandingSocialProof />
        <LandingFeatures />
        <LandingPricing demoMailto={demoMailto} salesMailto={salesMailto} />
        <LandingFinalCta demoMailto={demoMailto} salesMailto={salesMailto} />
      </main>
      <LandingFooter />
    </div>
  );
}
