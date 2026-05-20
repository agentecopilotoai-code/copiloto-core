/**
 * UI-INFLU-016 + UI-INFLU-016-FU — Landing público "Ravit Studio".
 *
 * Diseño basado en `docs/influencer/Ravit Studio Landing _standalone_.html`:
 *   - Paleta: bg #F1EDE3 · brand #2DBB6A · accent #0F7A3F · text #1B2542.
 *   - Tipografía: Geist (system fallback).
 *   - Logo oficial replicado como SVG inline en `assets/illustrations.jsx`.
 *
 * Secciones: Hero · Stats · Cómo funciona · Casting de ejemplo · Pricing ·
 * Afiliados · CTA final · Footer.
 */
import styles from './RavitAgentPulse.module.css';
import {
  CastingIcon,
  GenerateIcon,
  HeroIllustration,
  MonetizeIcon,
  PersonaAvatar,
  RavitMark,
  ScheduleIcon,
} from './assets/illustrations.jsx';


const PERSONAJES_EJEMPLO = [
  { name: 'Sofía Vega', handle: '@sofia.studio', skin: '#E8C9A9', hair: '#3A2A20', accent: '#0F7A3F' },
  { name: 'Camila Ríos', handle: '@camila.rios', skin: '#C9956F', hair: '#1B2542', accent: '#2DBB6A' },
  { name: 'Valeria Soto', handle: '@val.soto', skin: '#A87651', hair: '#2A1810', accent: '#0F7A3F' },
  { name: 'Mia Aguilar', handle: '@mia.aguilar', skin: '#F4D7B8', hair: '#A06535', accent: '#2DBB6A' },
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


export function RavitAgentPulse({ demoMailto = 'mailto:demo@ravit.studio', loginHref = '/login' }) {
  return (
    <article className={styles.page} data-testid="ravit-agent-pulse">
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
          <HeroIllustration />
        </div>
      </section>

      <section className={styles.stats}>
        <Stat number="184" label="posts/mes" />
        <Stat number="2.4M" label="alcance promedio" />
        <Stat number="8.4%" label="engagement" />
        <Stat number="5 redes" label="por personaje" />
      </section>

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

      <section className={styles.castingSection}>
        <h2 className={styles.sectionTitle}>Tu casting esperando</h2>
        <p className={styles.sectionSub}>
          Crea personajes únicos. Cada uno con su voz, su look y su agenda.
        </p>
        <div className={styles.personaGrid}>
          {PERSONAJES_EJEMPLO.map((p) => (
            <div key={p.handle} className={styles.personaCard}>
              <PersonaAvatar {...p} />
            </div>
          ))}
        </div>
      </section>

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
