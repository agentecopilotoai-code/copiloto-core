/**
 * Landing público Ravit Studio — Agent Pulse.
 *
 * Refactor alineado con `docs/influencer/Ravit Studio Landing _pure HTML.html`.
 * Estructura: hero bento → trust strip → shift comparison → cómo funciona
 * + bonus → casting bento (6 cols) → use cases → pricing (3 planes) →
 * final CTA dark → footer multi-columna.
 *
 * Las tokens `--ra-*` viven en `ravit-tokens.css` (scoped al shell).
 */
import { adminPath } from '../../../services/adminSession.js';
import styles from './RavitAgentPulse.module.css';
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

const TRUST_BRANDS = [
  'MAISON 14', 'LUME', 'NUMÉRO', 'AURA',
  'LAGO', 'ATELIER NORTE', 'CIELO HOTELS',
];

const SHIFT_OLD_ROWS = [
  ['Coste', '€4,000–€12,000'],
  ['Tiempo', '48–72 horas'],
  ['Personal', 'Fotógrafo, modelo, estilista, retoque'],
  ['Repetir', 'Re-contratar todo + viaje'],
  ['Output', '20–40 imágenes finales'],
  ['Consistencia', 'Depende de quién dispare'],
];

const SHIFT_NEW_ROWS = [
  ['Coste', 'desde €0 · pago por crédito'],
  ['Tiempo', '30 segundos por imagen'],
  ['Personal', 'Solo tú · y la IA'],
  ['Repetir', 'Infinitas variaciones, 1 clic'],
  ['Output', 'Fotos, reels, stories, anuncios'],
  ['Consistencia', 'Misma cara · siempre · forever'],
];

const HOW_STEPS = [
  { eyebrow: 'Paso 1 · Cara', n: '01', title: 'Construyes la cara',
    desc: 'Elige rasgos, ojos, pelo, piel, edad. O sube una foto.' },
  { eyebrow: 'Pasos 2–5', n: '02', title: 'Defines su mundo',
    desc: 'Identidad, voz, marcas afiliadas, idiomas y plataformas.' },
  { eyebrow: 'Estudio', n: '03', title: 'Generas contenido',
    desc: 'Fotos, reels, stories, anuncios. Misma cara, infinitas escenas.' },
  { eyebrow: 'Calendario', n: '04', title: 'Publicas y vendes',
    desc: 'Auto-post a IG, TikTok, YouTube. Con captions y hashtags.' },
];

const CASTING = [
  { name: 'Sofía Vega', meta: ['Lifestyle · Resort', '24.7K seguidores'],
    brand: '×Maison14', img: sofiaDress, size: 'large', socials: true },
  { name: 'Valeria Soto', meta: ['Fashion · Editorial'],
    brand: '×Numéro', img: sofiaKitchen, size: 'wide' },
  { name: 'Camila Ruiz', meta: ['Beach · Joyería'],
    brand: '×Lago', img: sofiaBedroom, size: 'small' },
  { name: 'Emma Lin', meta: ['Beauty · Skincare'],
    brand: '×Lume', img: sofiaCar, size: 'small' },
  { name: 'Mia Castro', meta: ['Editorial · Arte'],
    brand: null, img: sofiaDress, size: 'small' },
];

const CASES = [
  { industry: 'Moda', img: sofiaKitchen,
    caption: 'Drop nuevo · outfit completo desde €49',
    result: '+312% engagement', cadence: '4 reels/semana' },
  { industry: 'Hotelería', img: sofiaDress,
    caption: 'Atardeceres en Tulum · suites desde €380',
    result: '94K vistas/post', cadence: '180 reservas' },
  { industry: 'Beauty', img: sofiaCar,
    caption: 'Rutina noche · 4 pasos clean',
    result: '+24% conversión', cadence: '2x ROAS' },
];

const PLANS = [
  {
    label: 'Starter', price: '€0', per: null,
    desc: 'Para probar Ravit y crear tu primer personaje.',
    features: [
      '1 personaje',
      '15 imágenes / mes',
      '3 reels cortos',
      'Resolución 720p',
      'Marca de agua Ravit',
    ],
    cta: 'Empezar gratis', featured: false,
  },
  {
    label: 'Creator', price: '€49', per: '/mes',
    desc: 'Para creadores y marcas que postean a diario.',
    features: [
      '3 personajes',
      '200 imágenes / mes',
      '20 reels verticales',
      '1080p · sin marca',
      '1 voz clonada',
      'Auto-post IG · TikTok',
    ],
    cta: 'Probar 14 días', featured: true,
  },
  {
    label: 'Agencia', price: '€199', per: '/mes',
    desc: 'Multi-marca, aprobaciones y volumen sin tope.',
    features: [
      'Marcas ilimitadas',
      '2,000 imágenes / mes',
      '200 reels / mes',
      'Voces ilimitadas',
      'API + Webhooks',
      'Roles y aprobaciones',
    ],
    cta: 'Hablar con ventas', featured: false,
  },
];

const FOOTER_COLS = [
  { title: 'Producto', links: ['Casting', 'Estudio', 'Calendario', 'Plataformas', 'Roadmap'] },
  { title: 'Estudio',  links: ['Galería', 'Casos', 'Blog', 'Comunidad'] },
  { title: 'Empresa',  links: ['Sobre nosotros', 'Contacto', 'Trabaja con nosotros'] },
  { title: 'Legal',    links: ['Términos', 'Privacidad', 'Política IA', 'Derechos de imagen'] },
];


export function RavitAgentPulse({
  demoMailto = 'mailto:demo@ravit.studio',
  loginHref = DEFAULT_LOGIN_HREF,
}) {
  return (
    <article className={styles.page} data-testid="ravit-agent-pulse">
      <HeroSection demoMailto={demoMailto} />
      <TrustSection />
      <ShiftSection />
      <HowItWorksSection demoMailto={demoMailto} />
      <CastingSection />
      <UseCasesSection />
      <PricingSection demoMailto={demoMailto} />
      <FinalCtaSection demoMailto={demoMailto} loginHref={loginHref} />
      <FooterSection />
    </article>
  );
}


/* ─── Icons ───────────────────────────────────────────────────────── */

const IconArrow = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12h14M13 6l6 6-6 6" />
  </svg>
);
const IconPlay = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M8 5v14l11-7z" fill="currentColor" />
  </svg>
);
const IconSparkle = ({ size = 13 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3l1.8 5.2 5.2 1.8-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
    <path d="M19 3v3M21 4.5h-3" />
  </svg>
);
const IconHeart = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 21s-7-4.5-9.5-9.2C.8 8.4 3 5 6.4 5c1.9 0 3.5 1 4.6 2.5C12.1 6 13.7 5 15.6 5 19 5 21.2 8.4 19.5 11.8 17 16.5 12 21 12 21z" fill="currentColor" />
  </svg>
);
const IconCheck = ({ size = 12 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7" />
  </svg>
);
const IconIg = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
    <rect x="3" y="3" width="18" height="18" rx="5" />
    <circle cx="12" cy="12" r="4" />
    <circle cx="17.5" cy="6.5" r="1" fill="currentColor" />
  </svg>
);
const IconTt = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M16 3v3.5a4.5 4.5 0 004.5 4.5V14a8 8 0 01-4.5-1.4V16a6 6 0 11-6-6h.5v3.5H10A2.5 2.5 0 1012.5 16V3H16z" fill="currentColor" />
  </svg>
);
const IconYt = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <rect x="2" y="6" width="20" height="12" rx="3" stroke="currentColor" strokeWidth="1.6" />
    <path d="M10 9.5v5l5-2.5z" fill="currentColor" />
  </svg>
);
const IconThreads = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3c5 0 8 3 8 8s-3 10-8 10-8-3-8-8c0-3.5 1.5-6 4-6 2 0 3 1 3 3v3c0 1.5 1 2.5 2.5 2.5 2 0 3.5-1.5 3.5-4 0-3-2-5-5-5" />
  </svg>
);
const IconX = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M18.244 3H21.5L14.06 11.55 22.83 21H16.06l-5.29-6.21L4.76 21H1.5l7.94-9.13L1.17 3h6.93l4.78 5.69L18.244 3z" fill="currentColor" />
  </svg>
);
const IconFb = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
    <path d="M14 8h3V4h-3c-2 0-3.5 1.5-3.5 3.5V10H8v4h2.5v8h4v-8H17l1-4h-3.5V8.5c0-.3.2-.5.5-.5z" fill="currentColor" />
  </svg>
);


function Eyebrow({ children }) {
  return (
    <span className={styles.eyebrow}>
      <span className={styles.eyebrowDot} aria-hidden="true" />
      {children}
    </span>
  );
}

function SectionHead({ eyebrow, h2, sub }) {
  return (
    <div className={styles.sectionHead}>
      <div className={styles.eyebrowWrap}><Eyebrow>{eyebrow}</Eyebrow></div>
      <h2 className={styles.sectionH2}>{h2}</h2>
      {sub && <p className={styles.sectionLede}>{sub}</p>}
    </div>
  );
}


/* ─── Hero ────────────────────────────────────────────────────────── */

function HeroSection({ demoMailto }) {
  return (
    <section className={styles.hero} aria-labelledby="hero-title">
      <div className={styles.heroGrid}>
        <div className={styles.heroCopy}>
          <Eyebrow>Casting de personajes con IA</Eyebrow>
          <h1 id="hero-title" className={styles.heroH1}>
            Tu marca,<br />
            con <span className={styles.heroAccent}>cara propia</span>.
          </h1>
          <p className={styles.heroLede}>
            Crea un influencer virtual a la medida de tu marca y produce
            fotos, reels y anuncios listos para Instagram, TikTok y
            WhatsApp. Sin shootings, sin modelos, sin drama.
          </p>

          <div className={styles.heroCtaRow}>
            <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnXl].join(' ')}>
              Crear mi personaje <IconArrow />
            </a>
            <a href="#how" className={[styles.btn, styles.btnGhost, styles.btnXl].join(' ')}>
              <IconPlay /> Ver demo · 90s
            </a>
          </div>

          <div className={styles.heroStats}>
            {HERO_STATS.map((s) => (
              <div key={s.label} className={styles.heroStat}>
                <div className={styles.heroStatValue}>{s.value}</div>
                <div className={styles.heroStatLabel}>{s.label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className={styles.heroBento}>
          <div className={styles.pulseTile}>
            <div>
              <span className={styles.pulseStatus}>
                <span className={styles.pulseStatusDot} aria-hidden="true" />
                EN PRODUCCIÓN
              </span>
              <div className={styles.pulseBig}>184 posts<br />esta semana</div>
              <div className={styles.pulseSubSoft}>5 personajes · 7 plataformas</div>
            </div>
            <div>
              <div className={styles.pulseReachLabel}>Alcance</div>
              <div className={styles.pulseReachValue}>12.4M</div>
              <div className={styles.pulseReachSub}>últimos 30 días</div>
            </div>
          </div>

          <figure className={[styles.heroCard, styles.heroCardMain].join(' ')}>
            <img src={sofiaDress} alt="Sofía Vega" loading="lazy" />
            <span className={styles.gradientBottom} aria-hidden="true" />
            <span className={styles.aiPill}>
              <IconSparkle size={11} /> AI · TUYO
            </span>
            <figcaption className={styles.heroCardCaption}>
              <div className={styles.heroCardName}>Sofía Vega</div>
              <div className={styles.heroCardMeta}>@sofiavega.studio · 24.7K</div>
            </figcaption>
          </figure>

          <figure className={[styles.heroCard, styles.heroCardSec].join(' ')}>
            <img src={sofiaKitchen} alt="Valeria" loading="lazy" />
            <span className={styles.gradientBottom} aria-hidden="true" />
            <figcaption className={styles.heroCardCaption}>
              <div className={styles.heroCardNameSm}>Valeria</div>
              <div className={styles.heroCardMetaSm}>Fashion · 42.1K</div>
            </figcaption>
          </figure>

          <figure className={[styles.heroCard, styles.heroCardTri].join(' ')}>
            <img src={sofiaCar} alt="Emma" loading="lazy" />
            <span className={styles.gradientBottom} aria-hidden="true" />
            <figcaption className={styles.heroCardCaption}>
              <div className={styles.heroCardNameSm}>Emma</div>
              <div className={styles.heroCardMetaSm}>Beauty · 15.3K</div>
            </figcaption>
          </figure>

          <div className={[styles.notif, styles.notifTl].join(' ')}>
            <span className={styles.notifIcon}><IconSparkle size={16} /></span>
            <div>
              <div className={styles.notifTitle}>+12 nuevas variaciones</div>
              <div className={styles.notifSub}>generadas en 28s · Sofía</div>
            </div>
          </div>
          <div className={[styles.notif, styles.notifBr].join(' ')}>
            <span className={[styles.notifIcon, styles.notifIconCoral].join(' ')}>
              <IconHeart />
            </span>
            <div>
              <div className={styles.notifTitle}>Reel viral · 94K vistas</div>
              <div className={styles.notifSub}>Valeria · front row AW26</div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


/* ─── Trust strip ─────────────────────────────────────────────────── */

function TrustSection() {
  return (
    <section className={styles.trust} aria-label="Marcas que confían en Ravit">
      <div className={styles.trustRow}>
        <div className={styles.trustIntro}>
          <span className={styles.monoLabel}>Marcas que producen con Ravit</span>
          Moda, hotelería, e-commerce, agencias y restaurantes.
        </div>
        <div className={styles.trustBrands}>
          {TRUST_BRANDS.map((b) => <span key={b}>{b}</span>)}
        </div>
      </div>
    </section>
  );
}


/* ─── Shift (old vs new) ──────────────────────────────────────────── */

function ShiftSection() {
  return (
    <section className={styles.shift} id="shift" aria-labelledby="shift-title">
      <SectionHead
        eyebrow="El shift"
        h2={<span id="shift-title">De €4,000 a un café.</span>}
        sub="Lo que antes costaba un shooting de un día completo, ahora cabe en una pestaña del navegador."
      />

      <div className={styles.shiftGrid}>
        <div className={[styles.shiftCard, styles.shiftCardOld].join(' ')}>
          <div className={styles.shiftHeader}>
            <span className={styles.monoLabel}>El método antiguo</span>
            <span className={styles.shiftRule} aria-hidden="true" />
          </div>
          <h3 className={styles.shiftH3Old}>Shooting tradicional</h3>
          <div className={styles.shiftRows}>
            {SHIFT_OLD_ROWS.map(([k, v]) => (
              <div key={k} className={styles.shiftRow}>
                <span className={styles.shiftK}>{k}</span>
                <span className={styles.shiftV}>{v}</span>
              </div>
            ))}
          </div>
        </div>

        <div className={[styles.shiftCard, styles.shiftCardNew].join(' ')}>
          <span className={styles.shiftGlow} aria-hidden="true" />
          <div className={styles.shiftHeader}>
            <span className={[styles.monoLabel, styles.monoGreenBright].join(' ')}>Con Ravit</span>
            <span className={styles.shiftRule} aria-hidden="true" />
            <span style={{ color: 'var(--ra-brand)' }}><IconSparkle size={16} /></span>
          </div>
          <h3 className={styles.shiftH3New}>Tu casting virtual</h3>
          <div className={styles.shiftRows}>
            {SHIFT_NEW_ROWS.map(([k, v]) => (
              <div key={k} className={styles.shiftRow}>
                <span className={styles.shiftK}>{k}</span>
                <span className={styles.shiftV}>{v}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}


/* ─── How it works ────────────────────────────────────────────────── */

function HowItWorksSection({ demoMailto }) {
  return (
    <section className={styles.how} id="how" aria-labelledby="how-title">
      <SectionHead
        eyebrow="Cómo funciona"
        h2={<span id="how-title">De cero a casting en 5 minutos.</span>}
        sub="No es magia. Son 5 pasos guiados, una preview en vivo y un personaje listo para postear hoy."
      />

      <div className={styles.howSteps}>
        {HOW_STEPS.map((step, i) => (
          <div key={step.title} className={styles.howStep}>
            <span className={[styles.monoLabel, styles.monoGreen].join(' ')}>{step.eyebrow}</span>
            <div className={styles.howN}>{step.n}</div>
            <h3 className={styles.howH3}>{step.title}</h3>
            <p className={styles.howP}>{step.desc}</p>
            {i < HOW_STEPS.length - 1 && (
              <span className={styles.howArrow} aria-hidden="true">
                <IconArrow size={12} />
              </span>
            )}
          </div>
        ))}
      </div>

      <div className={styles.howBonus}>
        <div>
          <span className={[styles.monoLabel, styles.monoGreenBright, styles.monoInline].join(' ')}>
            <IconSparkle size={13} /> Bonus
          </span>
          <h3 className={styles.howBonusH3}>Ravit aprende tu marca mientras posteas.</h3>
          <p className={styles.howBonusP}>
            Cada caption aprobado, cada foto descartada, cada hashtag manual
            entrena la voz de tu personaje. En 2 semanas escribe casi solo.
          </p>
        </div>
        <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnLg].join(' ')}>
          Probar gratis <IconArrow />
        </a>
      </div>
    </section>
  );
}


/* ─── Casting ─────────────────────────────────────────────────────── */

function CastingSection() {
  return (
    <section className={styles.casting} id="casting" aria-labelledby="casting-title">
      <SectionHead
        eyebrow="El casting"
        h2={<span id="casting-title">Influencers que son 100% tuyos.</span>}
        sub="Cada personaje mantiene cara, voz y estilo en cada render. Tú eres la agencia."
      />

      <div className={styles.castingGrid}>
        {CASTING.map((p) => (
          <article
            key={p.name}
            className={[
              styles.showcaseCard,
              p.size === 'large' && styles.showcaseLarge,
              p.size === 'wide' && styles.showcaseWide,
              p.size === 'small' && styles.showcaseSmall,
            ].filter(Boolean).join(' ')}
          >
            <img src={p.img} alt={p.name} loading="lazy" className={styles.showcaseImg} />
            <span className={styles.gradientBottomStrong} aria-hidden="true" />
            <div className={styles.showcaseTopbar}>
              <span className={styles.aiPillSubtle}>
                <IconSparkle size={10} /> AI
              </span>
              {p.brand && <span className={styles.brandPill}>{p.brand}</span>}
            </div>
            <div className={styles.showcaseBottom}>
              <div className={styles.showcaseName}>{p.name}</div>
              <div className={styles.showcaseMeta}>
                {p.meta.map((m, idx) => (
                  <span key={idx}>{idx > 0 && <span aria-hidden="true">·</span>} {m}</span>
                ))}
              </div>
              {p.socials && (
                <div className={styles.showcaseSocials} aria-label="Plataformas">
                  <IconIg /><IconTt /><IconYt /><IconThreads /><IconX />
                </div>
              )}
            </div>
          </article>
        ))}
      </div>

      <div className={styles.castingCta}>
        <a href="#start" className={[styles.btn, styles.btnGhost, styles.btnLg].join(' ')}>
          Ver casting completo <IconArrow />
        </a>
      </div>
    </section>
  );
}


/* ─── Use cases / Industries ──────────────────────────────────────── */

function UseCasesSection() {
  return (
    <section className={styles.cases} id="cases" aria-labelledby="cases-title">
      <SectionHead
        eyebrow="Industrias"
        h2={<span id="cases-title">Hecho para marcas que postean mucho.</span>}
        sub="Moda, hotelería, e-commerce, beauty, hospitality. Donde la cara importa, Ravit funciona."
      />

      <div className={styles.casesGrid}>
        {CASES.map((c) => (
          <article key={c.industry} className={styles.caseCard}>
            <div className={styles.casePhoto}>
              <img src={c.img} alt={c.industry} loading="lazy" />
              <span className={styles.gradientBottomStrong} aria-hidden="true" />
              <span className={styles.caseIndustry}>{c.industry}</span>
              <div className={styles.caseCaptionOverlay}>{c.caption}</div>
            </div>
            <div className={styles.caseBody}>
              <div className={styles.caseRow}>
                <div>
                  <div className={styles.monoLabel}>Resultado</div>
                  <div className={styles.caseResult}>{c.result}</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className={styles.monoLabel}>Cadencia</div>
                  <div className={styles.caseCadence}>{c.cadence}</div>
                </div>
              </div>
              <div className={styles.caseFooterRow}>
                <div className={styles.caseSocialsSoft}>
                  <IconIg /><IconTt /><IconYt /><IconThreads />
                </div>
                <span className={styles.caseSee}>
                  Ver caso <IconArrow />
                </span>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}


/* ─── Pricing ─────────────────────────────────────────────────────── */

function PricingSection({ demoMailto }) {
  return (
    <section className={styles.pricing} id="pricing" aria-labelledby="pricing-title">
      <SectionHead
        eyebrow="Precios"
        h2={<span id="pricing-title">Empieza gratis. Escala cuando vendas.</span>}
        sub="Suscripción mensual + créditos para generaciones. Los créditos nunca caducan. Cancela cuando quieras."
      />

      <div className={styles.pricingGrid}>
        {PLANS.map((p) => (
          <div
            key={p.label}
            className={[styles.plan, p.featured && styles.planBest].filter(Boolean).join(' ')}
          >
            {p.featured && <span className={styles.bestBadge}>El más elegido</span>}
            <div className={[styles.monoLabel, p.featured ? styles.monoGreenBright : styles.monoGreen].join(' ')}>
              {p.label}
            </div>
            <div className={styles.planPrice}>
              <span className={styles.planPriceNum}>{p.price}</span>
              {p.per && <span className={styles.planPricePer}>{p.per}</span>}
            </div>
            <p className={styles.planDesc}>{p.desc}</p>
            <div className={styles.planFeatures}>
              {p.features.map((f) => (
                <div key={f} className={styles.planFeature}>
                  <span className={styles.planTick}><IconCheck /></span>
                  <span>{f}</span>
                </div>
              ))}
            </div>
            <div className={styles.planCta}>
              <a
                href={demoMailto}
                className={[
                  styles.btn,
                  p.featured ? styles.btnPrimary : styles.btnGhost,
                  styles.btnLg,
                  styles.btnFull,
                ].join(' ')}
              >
                {p.cta} <IconArrow />
              </a>
            </div>
          </div>
        ))}
      </div>

      <div className={styles.pricingFoot}>
        Todos los planes incluyen <strong>etiquetado IA</strong>,{' '}
        <strong>auto-publish</strong> y <strong>biblioteca infinita</strong>.
      </div>
    </section>
  );
}


/* ─── Final CTA ───────────────────────────────────────────────────── */

function FinalCtaSection({ demoMailto, loginHref }) {
  return (
    <section className={styles.final}>
      <div className={styles.finalCard}>
        <span className={styles.finalGlow} aria-hidden="true" />

        <div className={styles.finalCopy}>
          <Eyebrow>Última llamada</Eyebrow>
          <h2 className={styles.finalH2}>
            Tu marca también puede tener<br />
            <span className={styles.finalAccent}>cara propia.</span>
          </h2>
          <p className={styles.finalP}>
            14 días gratis. Sin tarjeta. Tu primer personaje listo en 5
            minutos y tu primer reel en 30 segundos.
          </p>
          <div className={styles.finalCtaRow}>
            <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnXl].join(' ')}>
              Crear personaje gratis <IconArrow />
            </a>
            <span className={styles.finalAlt}>
              ó <a href={loginHref}>Iniciar sesión →</a>
            </span>
          </div>
        </div>

        <div className={styles.finalPortrait}>
          <img src={sofiaDress} alt="Personaje virtual" loading="lazy" />
        </div>
      </div>
    </section>
  );
}


/* ─── Footer ──────────────────────────────────────────────────────── */

function FooterSection() {
  return (
    <footer className={styles.footer}>
      <div className={styles.footerInner}>
        <div>
          <div className={styles.footerBrand}>
            <svg viewBox="0 0 80 80" width="32" height="32" aria-hidden="true">
              <path d="M40 8 C 60 14, 70 30, 64 50 C 58 66, 38 72, 22 64 C 6 56, 4 36, 14 24 C 22 14, 32 10, 40 8 Z" fill="#2DBB6A" />
              <circle cx="44" cy="28" r="3.4" fill="#FFFFFF" />
              <path d="M22 64 C 30 50, 38 38, 50 28" stroke="#0F7A3F" strokeWidth="1.4" fill="none" opacity=".4" />
            </svg>
            <div className={styles.footerWord}>
              <div className={styles.footerWordRavit}>Ravit</div>
              <div className={styles.footerWordStudio}>STUDIO</div>
            </div>
          </div>
          <p className={styles.footerBlurb}>
            El estudio de casting AI para marcas que quieren tener cara
            propia, postear sin parar y vender más.
          </p>
          <div className={styles.footerTransparency}>
            <IconSparkle size={12} /> Etiquetas de transparencia IA en cada export
          </div>
        </div>

        {FOOTER_COLS.map((col) => (
          <div key={col.title} className={styles.footerCol}>
            <span className={styles.monoLabel}>{col.title}</span>
            <div className={styles.footerLinks}>
              {col.links.map((l) => <a key={l} href="#">{l}</a>)}
            </div>
          </div>
        ))}
      </div>

      <div className={styles.footerBottom}>
        <span>© {new Date().getFullYear()} Ravit Studio · Madrid · Barcelona · CDMX</span>
        <div className={styles.footerSocials}>
          <IconIg /><IconTt /><IconYt /><IconX /><IconThreads /><IconFb />
        </div>
      </div>
    </footer>
  );
}
