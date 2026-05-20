import { useEffect } from 'react';

import { adminPath } from '../../../services/adminSession.js';
import { LandingFeatures } from './components/LandingFeatures.jsx';
import { LandingFinalCta } from './components/LandingFinalCta.jsx';
import { LandingFooter } from './components/LandingFooter.jsx';
import { LandingHeader } from './components/LandingHeader.jsx';
import { LandingHero } from './components/LandingHero.jsx';
import { LandingPricing } from './components/LandingPricing.jsx';
import { LandingSocialProof } from './components/LandingSocialProof.jsx';
import styles from './Landing.module.css';

/**
 * UI-016.4 / UI-017 — Landing comercial pre-login (público).
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
 *  - "Iniciar sesión" → `loginHref`. El default usa `adminPath('/admin/login')`
 *    (BFF redirect) que arranca el Auth0 Authorization Code Flow del panel
 *    (`app/admin/routes.py`): `/admin/login` → `https://<tenant>/authorize` →
 *    callback en `/admin/callback` → cookie de sesión → `IndexRedirect` enruta
 *    al home del rol. Pasando `loginHref` por prop se override en tests.
 *
 * UI-017 elimina el splash legacy del panel — antes el SPA pintaba una vista
 * intermedia arriba del router cuando `!isAuthenticated` y la landing nunca
 * se veía. Ahora el `<RouterProvider />` se monta siempre y esta vista cubre
 * todo el caso anónimo.
 */
const DEFAULT_DEMO_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Solicito%20demo%20CopilotoIA';
const DEFAULT_SALES_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Contacto%20ventas%20CopilotoIA';
const DEFAULT_LOGIN_HREF = adminPath('/admin/login');

const LANDING_PAGE_TITLE =
  'CopilotoIA — Agendamiento por IA · WhatsApp, Instagram y Messenger';

export function Landing({
  demoMailto = DEFAULT_DEMO_MAILTO,
  salesMailto = DEFAULT_SALES_MAILTO,
  loginHref = DEFAULT_LOGIN_HREF,
  embedded = false,
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
      {!embedded && (
        <LandingHeader
          loginHref={loginHref}
          demoMailto={demoMailto}
          salesMailto={salesMailto}
        />
      )}
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
