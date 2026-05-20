/**
 * UI-INFLU-016 + redesign — Landing público "Ravit Studio".
 *
 * Fotos reales de personajes virtuales (Grok-generated) en
 * `admin-panel/public/ravit/sofia-*.png` se usan en:
 *   - Hero: mockup de feed Instagram con la foto principal.
 *   - Casting: 4 fotos como 4 personajes ejemplo.
 *
 * Tokens canónicos `--influencer-*` (UI-INFLU-001) via
 * `RavitAgentPulse.module.css`.
 */
import { adminPath } from '../../../services/adminSession.js';
import styles from './RavitAgentPulse.module.css';
import {
  CastingIcon,
  GenerateIcon,
  MonetizeIcon,
  RavitMark,
  ScheduleIcon,
} from './assets/illustrations.jsx';
import sofiaKitchen from './assets/images/sofia-kitchen.png';
import sofiaBedroom from './assets/images/sofia-bedroom.png';
import sofiaCar from './assets/images/sofia-car.png';
import sofiaDress from './assets/images/sofia-dress.png';


const DEFAULT_LOGIN_HREF = adminPath('/admin/login');

const PERSONAJES_EJEMPLO = [
  { name: 'Sofía Vega', handle: '@sofia.studio', tag: 'Lifestyle', image: sofiaKitchen },
  { name: 'Camila Ríos', handle: '@camila.rios', tag: 'Fashion', image: sofiaDress },
  { name: 'Valeria Soto', handle: '@val.soto', tag: 'Travel', image: sofiaCar },
  { name: 'Mia Aguilar', handle: '@mia.aguilar', tag: 'Beauty', image: sofiaBedroom },
];

const PASOS = [
  {
    icon: CastingIcon,
    titulo: 'Casting',
    desc: 'Crea tu personaje en 5 pasos: cara, cuerpo, identidad, voz y plataformas. 8 caras base o totalmente custom.',
  },
  {
    icon: GenerateIcon,
    titulo: 'Generar',
    desc: 'Fotos, reels, anuncios e historias con la voz y el look del personaje. Consistencia entre posts.',
  },
  {
    icon: ScheduleIcon,
    titulo: 'Programar',
    desc: 'Aprueba y agenda en el calendario semanal. Instagram, TikTok, YouTube — todo en un solo lugar.',
  },
  {
    icon: MonetizeIcon,
    titulo: 'Monetizar',
    desc: 'Conecta con marcas, paquetes premium, programa de afiliados. Etiqueta IA siempre visible.',
  },
];

const PRICING = [
  {
    label: 'Starter',
    price: '$29',
    creditos: '100 créditos',
    detail: '~12 reels o ~33 fotos',
    features: ['1 personaje', '1 plataforma conectada', 'Soporte por email'],
    featured: false,
  },
  {
    label: 'Pro',
    price: '$119',
    creditos: '500 créditos',
    detail: '~60 reels o ~166 fotos',
    features: ['3 personajes', '3 plataformas', 'Calendario semanal', 'Soporte prioritario'],
    featured: true,
  },
  {
    label: 'Studio',
    price: '$399',
    creditos: '2000 créditos',
    detail: '~250 reels o ~666 fotos',
    features: ['Personajes ilimitados', 'Todas las plataformas', 'API + webhooks', 'CSM dedicado'],
    featured: false,
  },
];


export function RavitAgentPulse({
  demoMailto = 'mailto:demo@ravit.studio',
  loginHref = DEFAULT_LOGIN_HREF,
}) {
  return (
    <article className={styles.page} data-testid="ravit-agent-pulse">
      {/* ─── Hero ─────────────────────────────────────────────────────── */}
      <section className={styles.hero}>
        <div className={styles.heroText}>
          <span className={styles.eyebrow}>Ravit Studio · Agent Pulse</span>
          <h1 className={styles.heroTitle}>
            Tu marca, <span className={styles.heroAccent}>con cara propia</span>.
          </h1>
          <p className={styles.heroSub}>
            Influencers virtuales que producen contenido por ti — cada día, en todas las redes.
            Fotos, reels, anuncios y voz, con la consistencia de un personaje que llevas tú.
          </p>
          <div className={styles.heroCtas}>
            <a href={demoMailto} className={styles.btnPrimary}>Solicitar demo</a>
            <a href={loginHref} className={styles.btnGhost}>Iniciar sesión</a>
          </div>
          <div className={styles.heroBadges}>
            <span className={styles.badge}>· Etiqueta IA visible</span>
            <span className={styles.badge}>· Persona consistency</span>
            <span className={styles.badge}>· Multi-plataforma</span>
          </div>
        </div>

        <div className={styles.heroArt}>
          <div className={styles.heroFeedMockup}>
            {/* Phone-like card with persona feed */}
            <div className={styles.feedHeader}>
              <div className={styles.feedAvatar}>
                <img src={sofiaKitchen} alt="Sofía Vega" />
              </div>
              <div className={styles.feedHeaderText}>
                <div className={styles.feedName}>Sofía Vega ✓</div>
                <div className={styles.feedHandle}>@sofia.studio · 124K seguidores</div>
              </div>
              <span className={styles.feedAiTag}>· AI</span>
            </div>
            <div className={styles.feedHeroImg}>
              <img src={sofiaDress} alt="Sofía en cocina con vestido azul" />
            </div>
            <div className={styles.feedActions}>
              <span>♡ 8.4K</span>
              <span>💬 142</span>
              <span>↗</span>
            </div>
            <div className={styles.feedCaption}>
              Domingo en casa, café en mano. Que tengas un día bonito 🌱
            </div>
          </div>
        </div>
      </section>

      {/* ─── Stats strip ─────────────────────────────────────────────── */}
      <section className={styles.stats}>
        <Stat number="184" label="posts/mes" />
        <Stat number="2.4M" label="alcance promedio" />
        <Stat number="8.4%" label="engagement" />
        <Stat number="5 redes" label="por personaje" />
      </section>

      {/* ─── Cómo funciona ───────────────────────────────────────────── */}
      <section className={styles.howSection}>
        <h2 className={styles.sectionTitle}>Cómo funciona</h2>
        <p className={styles.sectionSub}>De cero a tu primer post publicado en menos de una hora.</p>
        <ol className={styles.stepsGrid}>
          {PASOS.map((p, i) => {
            const IconComp = p.icon;
            return (
              <li key={p.titulo} className={styles.stepCard}>
                <div className={styles.stepHeader}>
                  <IconComp />
                  <span className={styles.stepNumber}>0{i + 1}</span>
                </div>
                <div className={styles.stepTitle}>{p.titulo}</div>
                <p className={styles.stepDesc}>{p.desc}</p>
              </li>
            );
          })}
        </ol>
      </section>

      {/* ─── Casting con fotos reales ─────────────────────────────────── */}
      <section className={styles.castingSection}>
        <h2 className={styles.sectionTitle}>Tu casting esperando</h2>
        <p className={styles.sectionSub}>
          Cada personaje único — con su voz, su look y su agenda. Consistencia entre posts.
        </p>
        <div className={styles.personaGrid}>
          {PERSONAJES_EJEMPLO.map((p) => (
            <figure key={p.handle} className={styles.personaCard}>
              <div className={styles.personaImageWrap}>
                <img src={p.image} alt={p.name} loading="lazy" />
                <span className={styles.personaAiBadge}>IA</span>
              </div>
              <figcaption className={styles.personaInfo}>
                <div className={styles.personaName}>{p.name}</div>
                <div className={styles.personaHandle}>{p.handle}</div>
                <span className={styles.personaTag}>{p.tag}</span>
              </figcaption>
            </figure>
          ))}
        </div>
      </section>

      {/* ─── Pricing ──────────────────────────────────────────────────── */}
      <section className={styles.pricingSection}>
        <h2 className={styles.sectionTitle}>Precios por paquete de créditos</h2>
        <p className={styles.sectionSub}>
          Cada generación cuesta créditos. Foto = 3 · Reel = 8 · Carrusel = 10.
        </p>
        <div className={styles.pricingGrid}>
          {PRICING.map((plan) => (
            <div
              key={plan.label}
              className={[styles.pricingCard, plan.featured ? styles.pricingCardFeatured : ''].join(' ')}
            >
              {plan.featured && <span className={styles.pricingTag}>MÁS POPULAR</span>}
              <div className={styles.pricingLabel}>{plan.label}</div>
              <div className={styles.pricingPrice}>{plan.price}</div>
              <div className={styles.pricingCreditos}>{plan.creditos}</div>
              <div className={styles.pricingDetail}>{plan.detail}</div>
              <ul className={styles.pricingFeatures}>
                {plan.features.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <a href={demoMailto} className={plan.featured ? styles.btnPrimary : styles.btnGhost}>
                Empezar
              </a>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Afiliados ────────────────────────────────────────────────── */}
      <section className={styles.affiliateSection}>
        <div className={styles.affiliateCard}>
          <RavitMark size={64} />
          <div className={styles.affiliateText}>
            <h2 className={styles.affiliateTitle}>Programa de afiliados</h2>
            <p className={styles.affiliateDesc}>
              Gana <strong>10%</strong> de cada cliente que refieras a Ravit Studio.
              Sin tope mensual, pagos automáticos.
            </p>
          </div>
          <a href={demoMailto} className={styles.btnPrimary}>Unirme</a>
        </div>
      </section>

      {/* ─── CTA final ────────────────────────────────────────────────── */}
      <section className={styles.ctaFinal}>
        <h2 className={styles.ctaFinalTitle}>¿Listo para conocer a tu personaje?</h2>
        <p className={styles.ctaFinalSub}>
          15 minutos de demo + setup guiado. Tu primer reel publicado en el día.
        </p>
        <div className={styles.heroCtas}>
          <a href={demoMailto} className={styles.btnPrimary}>Solicitar demo</a>
          <a href={loginHref} className={styles.btnGhost}>Iniciar sesión</a>
        </div>
      </section>

      <footer className={styles.footer}>
        <div className={styles.footerLeft}>
          <RavitMark size={36} />
          <span>Ravit Studio · {new Date().getFullYear()}</span>
        </div>
        <nav className={styles.footerLinks} aria-label="Links del footer">
          <a href="#privacy">Privacidad</a>
          <a href="#terms">Términos</a>
          <a href="#docs">Documentación</a>
        </nav>
      </footer>
    </article>
  );
}


function Stat({ number, label }) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statNumber}>{number}</div>
      <div className={styles.statLabel}>{label}</div>
    </div>
  );
}
