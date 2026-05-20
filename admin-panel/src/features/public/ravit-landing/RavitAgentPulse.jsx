/**
 * Landing público Ravit Studio — Agent Pulse.
 *
 * Layout bento asimétrico inspirado en `docs/influencer/Ravit Studio
 * Landing _standalone_.html`. Hero con stack de cards flotantes +
 * casting de 5 personajes con tags de marca.
 *
 * Todas las imágenes son `import` de Vite (resueltas con base path
 * `/admin/`). Tokens `--ra-*` se definen en `ravit-tokens.css` y se
 * scopean al shell — el tab CopilotoIA hereda la misma paleta.
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


const HERO_STATS = [
  { label: 'crear un personaje', value: '5 min' },
  { label: 'generar un reel', value: '30 seg' },
  { label: 'engagement medio', value: '+312%' },
];

const PASOS = [
  {
    icon: CastingIcon,
    titulo: 'Casting',
    desc: 'Crea tu personaje en 5 pasos: cara, cuerpo, identidad, voz y plataformas.',
  },
  {
    icon: GenerateIcon,
    titulo: 'Generar',
    desc: 'Fotos, reels, anuncios e historias con la voz y el look del personaje.',
  },
  {
    icon: ScheduleIcon,
    titulo: 'Programar',
    desc: 'Aprueba y agenda en el calendario semanal. IG, TikTok, YouTube en un solo lugar.',
  },
  {
    icon: MonetizeIcon,
    titulo: 'Monetizar',
    desc: 'Conecta con marcas, paquetes premium, programa de afiliados. Etiqueta IA visible.',
  },
];

const INDUSTRIAS = [
  { tag: 'Beauty', desc: 'Tutoriales, swatches, before/after sin shootings.' },
  { tag: 'Fashion', desc: 'Lookbooks editoriales y drops de temporada.' },
  { tag: 'Hospitality', desc: 'Resort, restaurante, hotel — content lifestyle local.' },
  { tag: 'Food & bev', desc: 'Reseñas, recetas, momentos de marca.' },
  { tag: 'Real estate', desc: 'Tours, walk-throughs, casos de éxito.' },
  { tag: 'Wellness', desc: 'Rutinas, productos, voz coherente con la marca.' },
];

const PRICING = [
  {
    label: 'Starter', price: '$29', creditos: '100 créditos',
    detail: '~12 reels o ~33 fotos',
    features: ['1 personaje', '1 plataforma conectada', 'Soporte por email'],
    featured: false,
  },
  {
    label: 'Pro', price: '$119', creditos: '500 créditos',
    detail: '~60 reels o ~166 fotos',
    features: ['3 personajes', '3 plataformas', 'Calendario semanal', 'Soporte prioritario'],
    featured: true,
  },
  {
    label: 'Studio', price: '$399', creditos: '2000 créditos',
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
      <HeroSection demoMailto={demoMailto} loginHref={loginHref} />
      <HowItWorksSection />
      <CastingSection />
      <IndustriesSection />
      <PricingSection demoMailto={demoMailto} />
      <AffiliatesSection demoMailto={demoMailto} />
      <CtaFinalSection demoMailto={demoMailto} loginHref={loginHref} />
      <FooterSection />
    </article>
  );
}


/* ─── Hero ────────────────────────────────────────────────────────── */

function HeroSection({ demoMailto, loginHref }) {
  return (
    <section className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.heroLeft}>
        <span className={styles.eyebrowPill}>● Casting de personajes con IA</span>
        <h1 id="hero-title" className={styles.heroTitle}>
          Tu marca, con <em>cara propia</em>.
        </h1>
        <p className={styles.heroSub}>
          Crea un influencer virtual a la medida de tu marca y produce fotos,
          reels y anuncios listos para Instagram, TikTok y WhatsApp. Sin
          shootings, sin modelos, sin drama.
        </p>
        <div className={styles.heroCtas}>
          <a href={demoMailto} className={styles.btnPrimary}>
            Crear mi personaje <span aria-hidden="true">→</span>
          </a>
          <a href={loginHref} className={styles.btnVideo}>
            <span className={styles.playIcon} aria-hidden="true">▶</span>
            Ver demo · 90s
          </a>
        </div>

        <div className={styles.heroStats}>
          {HERO_STATS.map((s) => (
            <div key={s.label} className={styles.heroStat}>
              <span className={styles.heroStatValue}>{s.value}</span>
              <span className={styles.heroStatLabel}>{s.label}</span>
            </div>
          ))}
        </div>
      </div>

      <div className={styles.heroRight}>
        {/* Floating card 1 — variaciones */}
        <div className={[styles.floatCard, styles.floatVariaciones].join(' ')}>
          <div className={styles.floatIcon}>✦</div>
          <div>
            <div className={styles.floatTitle}>+12 nuevas variaciones</div>
            <div className={styles.floatSub}>generadas en 28s · Sofía</div>
          </div>
        </div>

        {/* Main image — Sofía resort */}
        <figure className={[styles.heroImg, styles.heroImgMain].join(' ')}>
          <img src={sofiaDress} alt="Sofía Vega — Lifestyle resort" />
          <span className={styles.aiTag}>✧ AI · TUYO</span>
        </figure>

        {/* Card dark — posts esta semana */}
        <div className={styles.floatCardDark}>
          <span className={styles.statusDot}>● EN PRODUCCIÓN</span>
          <div className={styles.floatHeadline}>
            <span>184 posts</span>
            <small>esta semana</small>
          </div>
          <div className={styles.floatMeta}>5 personajes · 7 plataformas</div>
          <div className={styles.alcanceLabel}>ALCANCE</div>
          <figure className={[styles.heroImg, styles.heroImgInset].join(' ')}>
            <img src={sofiaBedroom} alt="Valeria · vestuario tropical" />
          </figure>
          <div className={styles.viralBadge}>
            <span className={styles.heartIcon}>♡</span>
            <div>
              <div className={styles.viralTitle}>Reel viral · 94K vistas</div>
              <div className={styles.viralMeta}>Valeria · front row AW26</div>
            </div>
          </div>
        </div>

        {/* Secondary image — Emma */}
        <figure className={[styles.heroImg, styles.heroImgSecondary].join(' ')}>
          <img src={sofiaCar} alt="Emma Lin · beauty skincare" />
        </figure>
      </div>
    </section>
  );
}


/* ─── Cómo funciona ───────────────────────────────────────────────── */

function HowItWorksSection() {
  return (
    <section className={styles.section} aria-labelledby="how-title">
      <span className={styles.eyebrowText}>Cómo funciona</span>
      <h2 id="how-title" className={styles.sectionTitle}>
        De cero a tu primer post publicado <em>en menos de una hora.</em>
      </h2>
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
  );
}


/* ─── Casting — bento asimétrico ──────────────────────────────────── */

function CastingSection() {
  return (
    <section className={styles.section} aria-labelledby="casting-title">
      <span className={styles.eyebrowText}>Influencers 100% tuyos</span>
      <h2 id="casting-title" className={styles.sectionTitle}>
        Casting <em>a la medida</em> de tu marca.
      </h2>
      <p className={styles.sectionSub}>
        Cada personaje tiene su voz, su look y su agenda. Consistencia entre
        posts. Etiqueta IA siempre visible.
      </p>

      <div className={styles.castingBento}>
        <figure className={[styles.castCard, styles.castMain].join(' ')}>
          <img src={sofiaDress} alt="Sofía Vega" loading="lazy" />
          <span className={styles.castAiBadge}>✧ AI</span>
          <span className={styles.castBrandTag}>×Maison14</span>
          <figcaption className={styles.castCaption}>
            <div className={styles.castName}>Sofía Vega</div>
            <div className={styles.castMeta}>
              <span>Lifestyle · Resort</span>
              <span>·</span>
              <span>24.7K seguidores</span>
            </div>
            <div className={styles.castSocials} aria-label="Plataformas">
              <span>◉</span><span>♪</span><span>►</span><span>○</span><span>𝕏</span>
            </div>
          </figcaption>
        </figure>

        <figure className={[styles.castCard, styles.castTopRight].join(' ')}>
          <img src={sofiaKitchen} alt="Valeria Soto" loading="lazy" />
          <span className={styles.castAiBadge}>✧ AI</span>
          <span className={styles.castBrandTag}>×Numéro</span>
          <figcaption className={styles.castCaptionLight}>
            <div className={styles.castName}>Valeria Soto</div>
            <div className={styles.castMeta}>Fashion · Editorial</div>
          </figcaption>
        </figure>

        <figure className={[styles.castCard, styles.castSmall].join(' ')}>
          <img src={sofiaBedroom} alt="Camila Ruiz" loading="lazy" />
          <span className={styles.castAiBadge}>✧ AI</span>
          <span className={styles.castBrandTag}>×Lago</span>
          <figcaption className={styles.castCaptionLight}>
            <div className={styles.castName}>Camila Ruiz</div>
            <div className={styles.castMeta}>Beach · Joyería</div>
          </figcaption>
        </figure>

        <figure className={[styles.castCard, styles.castSmall, styles.castGreen].join(' ')}>
          <img src={sofiaCar} alt="Emma Lin" loading="lazy" />
          <span className={styles.castAiBadge}>✧ AI</span>
          <span className={styles.castBrandTag}>×Lume</span>
          <figcaption className={styles.castCaptionLight}>
            <div className={styles.castName}>Emma Lin</div>
            <div className={styles.castMeta}>Beauty · Skincare</div>
          </figcaption>
        </figure>

        <figure className={[styles.castCard, styles.castSmall, styles.castGreen].join(' ')}>
          <img src={sofiaDress} alt="Mia Castro" loading="lazy" />
          <span className={styles.castAiBadge}>✧ AI</span>
          <figcaption className={styles.castCaptionLight}>
            <div className={styles.castName}>Mia Castro</div>
            <div className={styles.castMeta}>Editorial · Arte</div>
          </figcaption>
        </figure>
      </div>

      <div className={styles.castingFooter}>
        <button type="button" className={styles.btnGhostLg}>
          Ver casting completo <span aria-hidden="true">→</span>
        </button>
      </div>
    </section>
  );
}


/* ─── Industrias ──────────────────────────────────────────────────── */

function IndustriesSection() {
  return (
    <section className={styles.section} aria-labelledby="industries-title">
      <span className={styles.eyebrowText}>Industrias</span>
      <h2 id="industries-title" className={styles.sectionTitle}>
        Para marcas que <em>producen contenido cada día.</em>
      </h2>
      <ul className={styles.industriesGrid}>
        {INDUSTRIAS.map((i) => (
          <li key={i.tag} className={styles.industryCard}>
            <div className={styles.industryTag}>{i.tag}</div>
            <p className={styles.industryDesc}>{i.desc}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}


/* ─── Pricing ─────────────────────────────────────────────────────── */

function PricingSection({ demoMailto }) {
  return (
    <section className={styles.section} aria-labelledby="pricing-title">
      <span className={styles.eyebrowText}>Precios</span>
      <h2 id="pricing-title" className={styles.sectionTitle}>
        Paquetes de <em>créditos</em>, sin sorpresas.
      </h2>
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
            <a href={demoMailto} className={plan.featured ? styles.btnPrimary : styles.btnGhostLg}>
              Empezar
            </a>
          </div>
        ))}
      </div>
    </section>
  );
}


/* ─── Afiliados ──────────────────────────────────────────────────── */

function AffiliatesSection({ demoMailto }) {
  return (
    <section className={styles.section}>
      <div className={styles.affiliateCard}>
        <RavitMark size={56} />
        <div className={styles.affiliateText}>
          <div className={styles.affiliateEyebrow}>Programa de afiliados</div>
          <h2 className={styles.affiliateTitle}>Gana 10% por cada cliente que refieras.</h2>
          <p className={styles.affiliateDesc}>
            Sin tope mensual. Pagos automáticos a fin de mes. Dashboard de
            métricas en tu cuenta.
          </p>
        </div>
        <a href={demoMailto} className={styles.btnPrimary}>
          Unirme <span aria-hidden="true">→</span>
        </a>
      </div>
    </section>
  );
}


/* ─── CTA final ──────────────────────────────────────────────────── */

function CtaFinalSection({ demoMailto, loginHref }) {
  return (
    <section className={styles.ctaFinal}>
      <h2 className={styles.ctaFinalTitle}>
        ¿Listo para conocer a <em>tu personaje</em>?
      </h2>
      <p className={styles.ctaFinalSub}>
        15 minutos de demo + setup guiado. Tu primer reel publicado en el día.
      </p>
      <div className={styles.heroCtas}>
        <a href={demoMailto} className={styles.btnPrimary}>
          Crear mi personaje <span aria-hidden="true">→</span>
        </a>
        <a href={loginHref} className={styles.btnVideo}>Iniciar sesión</a>
      </div>
    </section>
  );
}


/* ─── Footer ─────────────────────────────────────────────────────── */

function FooterSection() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerLeft}>
        <RavitMark size={32} />
        <span>Ravit Studio · {new Date().getFullYear()}</span>
      </div>
      <nav className={styles.footerLinks} aria-label="Links del footer">
        <a href="#privacy">Privacidad</a>
        <a href="#terms">Términos</a>
        <a href="#docs">Documentación</a>
      </nav>
    </footer>
  );
}
