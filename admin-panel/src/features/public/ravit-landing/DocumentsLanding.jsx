/**
 * Landing público Gestión Documental AI.
 *
 * Estructura visual idéntica a `Landing.jsx` (Chatbot AI) y
 * `RavitAgentPulse.jsx` (Personajes AI). Copy genérico inventado —
 * pendiente de revisión con el producto real.
 *
 * Reusa el módulo CSS compartido `landing-shared.module.css`.
 */
import { adminPath } from '../../../services/adminSession.js';
import styles from './landing-shared.module.css';


const DEFAULT_DEMO_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Solicito%20demo%20Gesti%C3%B3n%20Documental';
const DEFAULT_SALES_MAILTO =
  'mailto:ventas@copilotoia.com?subject=Contacto%20ventas%20Gesti%C3%B3n%20Documental';
const DEFAULT_LOGIN_HREF = adminPath('/admin/login');


const HERO_STATS = [
  { label: 'procesar un documento', value: '12 seg' },
  { label: 'extracción correcta', value: '99.2%' },
  { label: 'reducción tiempo manual', value: '−85%' },
];

const TRUST_BRANDS = [
  'CONTADOR ASOC', 'LEGAL & CO', 'PYME PRO',
  'FACTURA HUB', 'AUDITA MX', 'NÓMINA AR', 'TAX BOGOTÁ',
];

const SHIFT_OLD_ROWS = [
  ['Tiempo por documento', '8–15 minutos manual'],
  ['Errores de tipeo', '2–5% inevitable'],
  ['Búsqueda', 'Carpetas, Excel, memoria'],
  ['Validación', 'Ojo humano página por página'],
  ['Auditoría', 'Re-revisión completa anual'],
  ['Volumen', 'Limita la operación'],
];

const SHIFT_NEW_ROWS = [
  ['Tiempo por documento', '< 15 segundos automático'],
  ['Errores de tipeo', '0% en campos validados'],
  ['Búsqueda', 'Texto libre · semántica IA'],
  ['Validación', 'Cross-check con reglas + ledger'],
  ['Auditoría', 'Trazabilidad continua en tiempo real'],
  ['Volumen', 'Miles de docs/día sin sumar gente'],
];

const HOW_STEPS = [
  { eyebrow: 'Paso 1 · Subir', n: '01', title: 'Subes el documento',
    desc: 'PDF, foto del celular, escaneo, email entrante. Cualquier formato.' },
  { eyebrow: 'Paso 2 · Extraer', n: '02', title: 'La IA extrae los datos',
    desc: 'Campos clave, totales, fechas, RUT/NIT, partidas, firmas. OCR + LLM.' },
  { eyebrow: 'Paso 3 · Validar', n: '03', title: 'Valida contra tus reglas',
    desc: 'Cross-check con catálogos, montos límite, duplicados, anti-fraude.' },
  { eyebrow: 'Paso 4 · Archivar', n: '04', title: 'Archiva y notifica',
    desc: 'A tu ERP, contable, repositorio fiscal — con búsqueda semántica.' },
];

const DOC_TYPES = [
  { name: 'Facturas',         desc: 'Electrónicas, PDF, foto. Captura totales, retenciones, ítems.', highlight: true },
  { name: 'Contratos',        desc: 'Cláusulas, fechas clave, partes, vencimientos, anexos.' },
  { name: 'Recibos / Boletas', desc: 'Conciliación contra gastos de tarjeta, viáticos, caja chica.' },
  { name: 'Estados de cuenta', desc: 'Movimientos bancarios, conciliación, alertas de anomalía.' },
];

const CASES = [
  { industry: 'Contables',
    caption: 'Cierre mensual sin horas extra',
    result: '−85% tiempo manual', cadence: '2,400 facturas/mes' },
  { industry: 'Legal',
    caption: 'Revisión de contratos en minutos',
    result: '40× más rápido', cadence: '99.4% precisión' },
  { industry: 'Auditoría',
    caption: 'Trazabilidad continua sin re-trabajo',
    result: 'SOC 2 ready', cadence: 'Audit log inmutable' },
];

const PLANS = [
  {
    label: 'Starter', price: 'USD $99', per: '/mes',
    desc: 'Para PYMEs que empiezan a digitalizar su backoffice.',
    features: [
      '1 usuario · 1 tipo de documento',
      'Hasta 200 documentos / mes',
      'Extracción + validación básica',
      'Export CSV / Excel',
      'Soporte por email',
    ],
    cta: 'Empezar gratis', featured: false,
  },
  {
    label: 'Business', price: 'USD $299', per: '/mes',
    desc: 'Para equipos de contabilidad, legal y operaciones.',
    features: [
      'Hasta 10 usuarios',
      '2,000 documentos / mes',
      'Todos los tipos de documento',
      'Reglas custom + cross-check ERP',
      'Búsqueda semántica + audit log',
      'Integraciones (QuickBooks, Siigo, SAP)',
    ],
    cta: 'Probar 14 días', featured: true,
  },
  {
    label: 'Enterprise', price: 'A medida', per: null,
    desc: 'Operaciones reguladas, volumen alto y compliance estricto.',
    features: [
      'Usuarios ilimitados · multi-tenant',
      'Documentos ilimitados',
      'On-premise / data residency',
      'SLA 99.9% + SSO + audit forense',
      'Modelos custom entrenados con tu data',
      'Roadmap conjunto + CSM dedicado',
    ],
    cta: 'Hablar con ventas', featured: false, isEnterprise: true,
  },
];

const FOOTER_COLS = [
  { title: 'Producto',     links: ['Extracción', 'Validación', 'Búsqueda IA', 'Audit log', 'Integraciones'] },
  { title: 'Documentos',   links: ['Facturas', 'Contratos', 'Recibos', 'Estados de cuenta', 'Nóminas'] },
  { title: 'Empresa',      links: ['Sobre nosotros', 'Casos de éxito', 'Blog', 'Contacto'] },
  { title: 'Legal',        links: ['Términos', 'Privacidad', 'Política IA', 'Compliance'] },
];


export function DocumentsLanding({
  demoMailto = DEFAULT_DEMO_MAILTO,
  salesMailto = DEFAULT_SALES_MAILTO,
  loginHref = DEFAULT_LOGIN_HREF,
}) {
  return (
    <article className={styles.page} data-testid="documents-landing">
      <HeroSection demoMailto={demoMailto} />
      <TrustSection />
      <ShiftSection />
      <HowItWorksSection demoMailto={demoMailto} />
      <DocTypesSection />
      <UseCasesSection />
      <PricingSection demoMailto={demoMailto} salesMailto={salesMailto} />
      <FinalCtaSection
        demoMailto={demoMailto}
        salesMailto={salesMailto}
        loginHref={loginHref}
      />
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
const IconCheck = ({ size = 12 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12.5l4.5 4.5L19 7" />
  </svg>
);
const IconDoc = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6" />
    <path d="M8 13h8M8 17h6" />
  </svg>
);
const IconContract = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <path d="M14 2v6h6M8 13h8M8 17h4M16 20l3-3-1.5-1.5L14.5 19v1.5H16v-.5z" />
  </svg>
);
const IconReceipt = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M4 2l2 2 2-2 2 2 2-2 2 2 2-2 2 2 2-2v20l-2-2-2 2-2-2-2 2-2-2-2 2-2-2-2 2z" />
    <path d="M8 10h8M8 14h8M8 18h5" />
  </svg>
);
const IconBank = ({ size = 28 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
       stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"
       strokeLinejoin="round" aria-hidden="true">
    <path d="M3 21h18M5 21V10M19 21V10M3 10l9-7 9 7M8 14v3M12 14v3M16 14v3" />
  </svg>
);
const IconX = ({ size = 12 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M18.244 3H21.5L14.06 11.55 22.83 21H16.06l-5.29-6.21L4.76 21H1.5l7.94-9.13L1.17 3h6.93l4.78 5.69L18.244 3z" fill="currentColor" />
  </svg>
);
const IconLn = ({ size = 14 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path d="M4 4h4v16H4zM6 2a2 2 0 110 4 2 2 0 010-4zM10 8h4v2.2c.7-1.2 2-2.4 4-2.4 3 0 4 2 4 5V20h-4v-6c0-1.4-.5-2.6-2-2.6S14 12.5 14 14v6h-4V8z" fill="currentColor" />
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


/* ─── Hero con doc preview card ──────────────────────────────────── */

function HeroSection({ demoMailto }) {
  return (
    <section className={styles.hero} aria-labelledby="doc-hero-title">
      <div className={styles.heroGrid}>
        <div className={styles.heroCopy}>
          <Eyebrow>Gestión Documental AI · OCR + LLM + Audit</Eyebrow>
          <h1 id="doc-hero-title" className={styles.heroH1}>
            Sube un PDF.
            <br />
            Lo demás lo hace{' '}
            <span className={styles.heroAccent}>la IA.</span>
          </h1>
          <p className={styles.heroLede}>
            Extracción de datos, validación contra tus reglas, búsqueda
            semántica y archivo automático. Facturas, contratos, recibos
            o estados de cuenta — en segundos, con trazabilidad completa.
          </p>

          <div className={styles.heroCtaRow}>
            <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnXl].join(' ')}>
              Procesar mi primer documento <IconArrow />
            </a>
            <a href="#features" className={[styles.btn, styles.btnGhost, styles.btnXl].join(' ')}>
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
          <DocPreviewCard />
        </div>
      </div>
    </section>
  );
}


function DocPreviewCard() {
  return (
    <div className={styles.chatCard} aria-label="Preview de documento procesado">
      <div className={styles.chatHeader}>
        <div className={styles.chatAvatar} aria-hidden="true">
          <IconDoc size={20} />
        </div>
        <div>
          <div className={styles.chatTitle}>Factura · ACME S.A.S.</div>
          <div className={styles.chatStatus}>
            <span className={styles.chatStatusDot} aria-hidden="true" />
            Procesada · 12 segundos · 99.4% confianza
          </div>
        </div>
      </div>

      <div className={styles.chatBody}>
        <ChatBubble side="bot">
          📄 <strong>Documento detectado:</strong> Factura electrónica<br />
          <strong>RUT emisor:</strong> 900.123.456-7<br />
          <strong>Fecha:</strong> 14 mayo 2026
        </ChatBubble>

        <ChatBubble side="bot">
          <strong>12 ítems</strong> extraídos · subtotal $4,820,000<br />
          IVA 19%: $915,800 · <strong>Total: $5,735,800</strong>
        </ChatBubble>

        <ChatBubble side="bot" highlight>
          ✓ Cross-check OK · sin duplicados<br />
          ✓ Dentro de límite del proveedor<br />
          ✓ Enviado a QuickBooks · archivada
        </ChatBubble>

        <div className={styles.chatMeta}>
          ledger · 14 may 11:08 utc
        </div>
      </div>

      <div className={styles.chatFooter}>
        <span className={styles.chatChip}><IconDoc size={11} /> Factura</span>
        <span className={styles.chatChip}><IconContract size={11} /> Contrato</span>
        <span className={styles.chatChip}><IconReceipt size={11} /> Recibo</span>
        <span className={styles.chatChip}><IconBank size={11} /> Bancario</span>
      </div>
    </div>
  );
}

function ChatBubble({ side, highlight, children }) {
  const classes = [
    styles.chatBubble,
    side === 'user' ? styles.chatBubbleUser : styles.chatBubbleBot,
    highlight && styles.chatBubbleHighlight,
  ].filter(Boolean).join(' ');
  return <div className={classes}>{children}</div>;
}


/* ─── Trust strip ─────────────────────────────────────────────────── */

function TrustSection() {
  return (
    <section className={styles.trust} aria-label="Equipos que procesan documentos con IA">
      <div className={styles.trustRow}>
        <div className={styles.trustIntro}>
          <span className={styles.monoLabel}>Contadores, equipos legales y operaciones que ya automatizan</span>
          Más de 40 firmas procesan documentos críticos con nosotros.
        </div>
        <div className={styles.trustBrands}>
          {TRUST_BRANDS.map((b) => <span key={b}>{b}</span>)}
        </div>
      </div>
    </section>
  );
}


/* ─── Shift ───────────────────────────────────────────────────────── */

function ShiftSection() {
  return (
    <section className={styles.shift} aria-labelledby="doc-shift-title">
      <SectionHead
        eyebrow="El shift"
        h2={<span id="doc-shift-title">De 10 minutos a 12 segundos.</span>}
        sub="Lo que antes ocupaba un asistente toda la tarde, ahora pasa solo. Tu equipo dedica el tiempo a decidir, no a tipear."
      />

      <div className={styles.shiftGrid}>
        <div className={[styles.shiftCard, styles.shiftCardOld].join(' ')}>
          <div className={styles.shiftHeader}>
            <span className={styles.monoLabel}>Backoffice tradicional</span>
            <span className={styles.shiftRule} aria-hidden="true" />
          </div>
          <h3 className={styles.shiftH3Old}>Captura manual</h3>
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
            <span className={[styles.monoLabel, styles.monoGreenBright].join(' ')}>Con Gestión Documental AI</span>
            <span className={styles.shiftRule} aria-hidden="true" />
            <span style={{ color: 'var(--ra-brand)' }}><IconSparkle size={16} /></span>
          </div>
          <h3 className={styles.shiftH3New}>Tu pipeline automatizado</h3>
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


/* ─── How it works ───────────────────────────────────────────────── */

function HowItWorksSection({ demoMailto }) {
  return (
    <section className={styles.how} id="features" aria-labelledby="doc-how-title">
      <SectionHead
        eyebrow="Cómo funciona"
        h2={<span id="doc-how-title">De PDF a archivado en menos de un minuto.</span>}
        sub="Cuatro pasos automatizados con humano en el loop sólo cuando hay duda. Auditoría continua incluida."
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
          <h3 className={styles.howBonusH3}>El modelo aprende tus reglas de negocio.</h3>
          <p className={styles.howBonusP}>
            Cada corrección manual, cada excepción aprobada, cada nuevo
            tipo de documento entrena al sistema. En 30 días la tasa de
            intervención humana baja del 15% al 2%.
          </p>
        </div>
        <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnLg].join(' ')}>
          Probar gratis <IconArrow />
        </a>
      </div>
    </section>
  );
}


/* ─── Tipos de documento ──────────────────────────────────────────── */

function DocTypesSection() {
  const icons = [IconDoc, IconContract, IconReceipt, IconBank];
  return (
    <section className={styles.casting} aria-labelledby="doc-types-title">
      <SectionHead
        eyebrow="Tipos de documento"
        h2={<span id="doc-types-title">Procesa todo lo que pase por tu mesa.</span>}
        sub="Modelos pre-entrenados + plantillas custom. Si tu documento existe, lo entendemos."
      />

      <div className={styles.channelsGrid}>
        {DOC_TYPES.map((doc, i) => {
          const Icon = icons[i] || IconDoc;
          return (
            <div
              key={doc.name}
              className={[styles.channelCard, doc.highlight && styles.channelCardHighlight].filter(Boolean).join(' ')}
            >
              <span className={styles.channelIcon}><Icon size={28} /></span>
              <div className={styles.channelName}>{doc.name}</div>
              <p className={styles.channelDesc}>{doc.desc}</p>
            </div>
          );
        })}
      </div>
    </section>
  );
}


/* ─── Use cases ───────────────────────────────────────────────────── */

function UseCasesSection() {
  return (
    <section className={styles.cases} aria-labelledby="doc-cases-title">
      <SectionHead
        eyebrow="Casos de uso"
        h2={<span id="doc-cases-title">Hecho para equipos que procesan documentos críticos.</span>}
        sub="Contabilidad, jurídico, auditoría, compliance, operaciones reguladas."
      />

      <div className={styles.casesGrid}>
        {CASES.map((c) => (
          <article key={c.industry} className={styles.caseCard}>
            <div className={[styles.casePhoto, styles.casePlaceholder].join(' ')}>
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
                  <div className={styles.monoLabel}>Métrica</div>
                  <div className={styles.caseCadence}>{c.cadence}</div>
                </div>
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}


/* ─── Pricing ─────────────────────────────────────────────────────── */

function PricingSection({ demoMailto, salesMailto }) {
  return (
    <section className={styles.pricing} aria-labelledby="doc-pricing-title">
      <SectionHead
        eyebrow="Precios"
        h2={<span id="doc-pricing-title">Pagas por documento procesado, no por sentarte.</span>}
        sub="14 días de prueba sin tarjeta. Documentos no usados no se acumulan, pero el plan se ajusta cada mes."
      />

      <div className={styles.pricingGrid}>
        {PLANS.map((p) => (
          <div
            key={p.label}
            className={[styles.plan, p.featured && styles.planBest].filter(Boolean).join(' ')}
            aria-labelledby={`doc-plan-${p.label}`}
          >
            {p.featured && <span className={styles.bestBadge}>Más elegido</span>}
            <h3
              id={`doc-plan-${p.label}`}
              className={[styles.monoLabel, p.featured ? styles.monoGreenBright : styles.monoGreen].join(' ')}
              style={{ margin: 0 }}
            >
              {p.label}
            </h3>
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
                href={p.isEnterprise ? salesMailto : demoMailto}
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
        Todos los planes incluyen <strong>cifrado en tránsito y reposo</strong>,{' '}
        <strong>audit log inmutable</strong> y <strong>compliance SOC 2 ready</strong>.
      </div>
    </section>
  );
}


/* ─── Final CTA ───────────────────────────────────────────────────── */

function FinalCtaSection({ demoMailto, salesMailto, loginHref }) {
  return (
    <section className={styles.final} aria-labelledby="doc-final-title">
      <div className={styles.finalCard}>
        <span className={styles.finalGlow} aria-hidden="true" />

        <div className={styles.finalCopy}>
          <Eyebrow>14 días gratis · sin tarjeta</Eyebrow>
          <h2 id="doc-final-title" className={styles.finalH2}>
            Deja de tipear.<br />
            <span className={styles.finalAccent}>Empieza a decidir.</span>
          </h2>
          <p className={styles.finalP}>
            Sube tu primer documento en menos de 30 segundos. Si te
            sirve, sigue. Si no, no nos debes nada. Setup completo en
            una mañana.
          </p>
          <div className={styles.finalCtaRow}>
            <a href={demoMailto} className={[styles.btn, styles.btnPrimary, styles.btnXl].join(' ')}>
              Probar gratis <IconArrow />
            </a>
            <a href={salesMailto} className={[styles.btn, styles.btnGhost, styles.btnXl].join(' ')}>
              Hablar con ventas
            </a>
            <span className={styles.finalAlt}>
              ó <a href={loginHref}>Iniciar sesión →</a>
            </span>
          </div>
        </div>

        <div className={styles.finalPortrait}>
          <div className={[styles.chatCard, styles.chatCardCompact].join(' ')}>
            <div className={styles.chatHeader}>
              <div className={styles.chatAvatar} aria-hidden="true">
                <IconDoc size={18} />
              </div>
              <div>
                <div className={styles.chatTitle}>+2,847 documentos</div>
                <div className={styles.chatStatus}>
                  <span className={styles.chatStatusDot} aria-hidden="true" />
                  procesados este mes · 99.2% precisión
                </div>
              </div>
            </div>
            <div className={styles.chatBody}>
              <ChatBubble side="bot">
                2,634 facturas · 142 contratos · 71 recibos. Sin un solo error de tipeo.
              </ChatBubble>
            </div>
          </div>
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
            </svg>
            <div className={styles.footerWord}>
              <div className={styles.footerWordRavit}>CopilotoIA</div>
              <div className={styles.footerWordStudio}>DOCS AI</div>
            </div>
          </div>
          <p className={styles.footerBlurb}>
            Procesamiento documental con IA para contadores, equipos
            legales y operaciones reguladas. Extracción, validación y
            archivo — con audit log y compliance.
          </p>
          <div className={styles.footerTransparency}>
            <IconSparkle size={12} /> SOC 2 ready · audit log inmutable
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
        <span>© {new Date().getFullYear()} CopilotoIA · Documental AI</span>
        <div className={styles.footerSocials}>
          <IconLn /><IconX />
        </div>
      </div>
    </footer>
  );
}
