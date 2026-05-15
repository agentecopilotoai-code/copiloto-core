import shared from '../Landing.module.css';
import styles from './LandingFeatures.module.css';

const FEATURES = [
  {
    title: 'Conecta tus canales',
    body:
      'WhatsApp Cloud API, Instagram DM, Facebook Messenger y un widget web embebible. Onboarding paso a paso, sin programar.',
    glyph: '01',
  },
  {
    title: 'El bot atiende y agenda',
    body:
      'Responde dudas, califica leads, ofrece servicios, agenda citas y manda recordatorios — entrenado con tu catálogo y políticas.',
    glyph: '02',
  },
  {
    title: 'Tu equipo solo lo importante',
    body:
      'El 84% se resuelve sin humano. El resto entra ordenado al Operations Desk con contexto completo del cliente.',
    glyph: '03',
  },
  {
    title: 'Agenda sin fricción',
    body:
      'El cliente elige fecha, hora, sede y profesional en la misma conversación. Confirmación instantánea en el canal donde empezó.',
    glyph: '04',
  },
  {
    title: 'Recordatorios automáticos',
    body:
      'Mensaje el día anterior, confirmación activa y reagendamiento sin llamadas. Reduce no-shows hasta 60%.',
    glyph: '05',
  },
  {
    title: 'CRM con historial 360°',
    body:
      'Cada contacto trae su historial, etiquetas, paquetes, suscripciones y nivel de consentimiento — listo para tu equipo.',
    glyph: '06',
  },
  {
    title: 'Campañas y segmentos',
    body:
      'Mensajes masivos a "inactivos 90d" o "cumpleaños mayo". Templates aprobados, métricas de entrega y atribución.',
    glyph: '07',
  },
  {
    title: 'Analítica accionable',
    body:
      'Funnel de captación a recompra, conversión por canal, ranking de agentes, ingreso atribuido por campaña.',
    glyph: '08',
  },
  {
    title: 'Cumplimiento real',
    body:
      'Doble opt-in Ley 1581 / GDPR, ledger auditable, retención configurable, exportes para derecho de acceso.',
    glyph: '09',
  },
];

/**
 * UI-016.4 — Sección de features. 9 cards en grid 3x3 (colapsa a 1 col bajo
 * 880px). Cada card: glyph numérico + título + body.
 *
 * El `id="features"` permite que el CTA "Ver cómo funciona" del hero ancle
 * acá vía `<a href="#features">`.
 */
export function LandingFeatures() {
  return (
    <section className={styles.features} id="features" aria-labelledby="landing-features-title">
      <div className={shared.container}>
        <div className={shared.sectionHeader}>
          <span className={shared.sectionTag}>Todo lo que necesitas</span>
          <h2 id="landing-features-title" className={shared.sectionTitle}>
            Una plataforma. Cero adhesivos.
          </h2>
          <p className={shared.sectionBody}>
            Diseñada para clínicas, spas, talleres, veterinarias y cualquier negocio que
            viva del agendamiento.
          </p>
        </div>

        <div className={styles.featuresGrid}>
          {FEATURES.map((feature) => (
            <article key={feature.title} className={styles.featureCard}>
              <span className={styles.featureIcon} aria-hidden="true">
                {feature.glyph}
              </span>
              <h3 className={styles.featureTitle}>{feature.title}</h3>
              <p className={styles.featureBody}>{feature.body}</p>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
