/**
 * UI-INFLU-016 — Contenido del tab "Ravit Agent · Pulse" (landing público).
 *
 * Usa tokens Ravit Studio (`var(--ra-*)`) configurados por UI-INFLU-001.
 */
export function RavitAgentPulse({ demoMailto = 'mailto:demo@ravit.studio', loginHref = '/login' }) {
  return (
    <article data-testid="ravit-agent-pulse" style={{
      background: 'var(--ra-bg, #F1EDE3)',
      color: 'var(--ra-text, #1B2542)',
      fontFamily: 'var(--ra-font, system-ui)',
      padding: 'var(--space-4) var(--space-3)',
    }}>
      <section aria-labelledby="ravit-hero" style={{ textAlign: 'center', padding: 'var(--space-5) 0' }}>
        <h1 id="ravit-hero" style={{
          fontSize: 'clamp(2rem, 5vw, 3.5rem)',
          fontWeight: 800,
          lineHeight: 1.1,
          margin: 0,
        }}>
          Influencers de IA que producen contenido por ti
        </h1>
        <p style={{
          marginTop: 'var(--space-3)',
          fontSize: '1.125rem',
          color: 'var(--ra-text-subtle, #4b5563)',
          maxWidth: 640, marginInline: 'auto',
        }}>
          Cada día, en todas las redes — fotos, reels, anuncios y voz, con la
          consistencia de un personaje virtual que llevas tú.
        </p>
        <div style={{ display: 'flex', gap: 'var(--space-2)', justifyContent: 'center', marginTop: 'var(--space-4)', flexWrap: 'wrap' }}>
          <a href={demoMailto} style={{
            background: 'var(--ra-brand, #2DBB6A)',
            color: '#fff',
            padding: '12px 24px',
            borderRadius: 8,
            textDecoration: 'none',
            fontWeight: 600,
          }}>Solicitar demo</a>
          <a href={loginHref} style={{
            background: 'transparent',
            color: 'var(--ra-text, #1B2542)',
            padding: '12px 24px',
            borderRadius: 8,
            border: '1px solid var(--ra-text, #1B2542)',
            textDecoration: 'none',
            fontWeight: 600,
          }}>Iniciar sesión</a>
        </div>
      </section>

      <section aria-labelledby="ravit-how" style={{ paddingTop: 'var(--space-4)' }}>
        <h2 id="ravit-how" style={{ textAlign: 'center', fontSize: '1.75rem' }}>Cómo funciona</h2>
        <ol style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
          gap: 'var(--space-3)', maxWidth: 1024, margin: 'var(--space-4) auto', padding: 0, listStyle: 'none',
        }}>
          {[
            { n: 1, t: 'Casting', d: 'Crea tu personaje en 5 pasos: cara, cuerpo, identidad, voz, plataformas.' },
            { n: 2, t: 'Generar', d: 'Fotos, reels, anuncios e historias — todo con la voz y look del personaje.' },
            { n: 3, t: 'Programar', d: 'Aprueba y agenda en el calendario semanal. IG, TikTok, YouTube en un solo lugar.' },
            { n: 4, t: 'Monetizar', d: 'Crece tu audiencia y conecta con marcas. Etiqueta IA siempre visible.' },
          ].map((step) => (
            <li key={step.n} style={{
              background: '#fff',
              padding: 'var(--space-3)',
              borderRadius: 12,
              border: '1px solid rgba(15, 122, 63, 0.1)',
            }}>
              <div style={{
                background: 'var(--ra-accent, #0F7A3F)',
                color: '#fff',
                width: 32, height: 32, borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontWeight: 700,
                marginBottom: 'var(--space-1)',
              }}>{step.n}</div>
              <div style={{ fontWeight: 700, fontSize: '1.125rem' }}>{step.t}</div>
              <p style={{ marginTop: 'var(--space-1)', color: 'var(--ra-text-subtle, #4b5563)' }}>{step.d}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="ravit-pricing" style={{ paddingTop: 'var(--space-4)', textAlign: 'center' }}>
        <h2 id="ravit-pricing" style={{ fontSize: '1.75rem' }}>Pricing por paquete de créditos</h2>
        <ul style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: 'var(--space-3)', maxWidth: 800, margin: 'var(--space-4) auto', padding: 0, listStyle: 'none',
        }}>
          {[
            { label: '100 créditos', price: '$29', detail: 'Starter · ~12 reels' },
            { label: '500 créditos', price: '$119', detail: 'Pro · ~60 reels' },
            { label: '2000 créditos', price: '$399', detail: 'Studio · ~250 reels' },
          ].map((plan) => (
            <li key={plan.label} style={{
              background: '#fff', padding: 'var(--space-3)', borderRadius: 12,
              border: '1px solid rgba(15, 122, 63, 0.1)',
            }}>
              <div style={{ fontWeight: 700 }}>{plan.label}</div>
              <div style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--ra-accent, #0F7A3F)' }}>
                {plan.price}
              </div>
              <div style={{ fontSize: 12, color: 'var(--ra-text-subtle, #4b5563)' }}>{plan.detail}</div>
            </li>
          ))}
        </ul>
      </section>

      <section aria-labelledby="ravit-affiliates" style={{
        paddingTop: 'var(--space-4)', textAlign: 'center', marginBottom: 'var(--space-5)',
      }}>
        <h2 id="ravit-affiliates" style={{ fontSize: '1.5rem' }}>Programa de afiliados</h2>
        <p style={{ color: 'var(--ra-text-subtle, #4b5563)', maxWidth: 480, margin: 'var(--space-2) auto' }}>
          Gana <strong>10%</strong> de cada cliente que refieras a Ravit Studio.
        </p>
      </section>
    </article>
  );
}
