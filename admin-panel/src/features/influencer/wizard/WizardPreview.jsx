/**
 * UI-INFLU-014.8 — WizardPreview persistente para steps 2-5 del wizard.
 *
 * Look textualmente idéntico a la columna izquierda del Step1Face
 * (preview grande con badge "VISTA PREVIA", overlay GENERACIÓN #NN /
 * nombre, tira de variaciones con borde verde en la activa, botón
 * "✦ Generar +1").
 *
 * No se usa en Step1Face — Step1Face mantiene su preview interno
 * porque el usuario ya aprobó ese diseño visual. Este componente
 * sólo añade persistencia visual del preview en steps 2-5.
 *
 * Props:
 *   personaName        — string overlay
 *   variations         — [{ id, url, canonical, marked_canonical }]
 *   onSelectVariation  — (id) => void
 *   onGenerate         — () => void
 *   pendingCount       — placeholders con spinner mientras Grok genera
 *   disabled           — desactiva el botón
 */
export function WizardPreview({
  personaName = 'Personaje en construcción',
  variations = [],
  onSelectVariation,
  onGenerate,
  pendingCount = 0,
  disabled = false,
}) {
  const ready = variations.filter((v) => v?.url);
  // Activa = la marcada canonical o la última generada.
  const active = ready.find((v) => v.canonical || v.marked_canonical) || ready[ready.length - 1];
  const previewUrl = active?.url;
  const generationNumber = String(ready.length || 1).padStart(2, '0');

  return (
    <div>
      {/* PREVIEW grande */}
      <div style={{
        position: 'relative', aspectRatio: '3/4',
        borderRadius: 14, overflow: 'hidden',
        background: 'linear-gradient(180deg, #c9b89a, #8b6f4e)',
        border: '1px solid #e6e0d4',
      }}>
        <div style={{
          position: 'absolute', top: 12, left: 12,
          background: '#fff', borderRadius: 999,
          padding: '4px 10px', fontSize: 11,
          fontWeight: 600, color: '#1b6f3e',
          display: 'flex', alignItems: 'center', gap: 4, zIndex: 2,
        }}>
          <span style={{ width: 8, height: 8, borderRadius: '50%', background: '#2DBB6A' }} />
          VISTA PREVIA
        </div>
        {previewUrl ? (
          <img src={previewUrl} alt="Vista previa"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : pendingCount > 0 ? (
          <div style={{
            position: 'absolute', inset: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <ThumbSpinner size={32} />
          </div>
        ) : null}
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: 'linear-gradient(transparent, rgba(0,0,0,0.6))',
          color: '#fff', padding: '24px 16px 12px',
        }}>
          <div style={{ fontSize: 10, letterSpacing: '0.08em', opacity: 0.8 }}>
            GENERACIÓN #{generationNumber}
          </div>
          <div style={{ fontSize: 18, fontWeight: 600 }}>{personaName}</div>
        </div>
      </div>

      {/* VARIACIONES */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        fontSize: 11, letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--ravit-text-muted, #777)', marginTop: 16, marginBottom: 8,
      }}>
        <span>VARIACIONES GENERADAS</span>
        <button
          type="button"
          onClick={onGenerate}
          disabled={disabled}
          aria-label="Generar nueva variación, cuesta 1 crédito"
          style={{
            background: 'transparent', border: 'none',
            cursor: disabled ? 'not-allowed' : 'pointer',
            opacity: disabled ? 0.5 : 1,
            fontSize: 12, color: '#2DBB6A', fontWeight: 600,
            textTransform: 'none', letterSpacing: 0,
            display: 'inline-flex', alignItems: 'center', gap: 4,
          }}
        >
          <span aria-hidden="true">✦</span>
          <span>Generar</span>
          <span aria-hidden="true" style={{
            background: 'rgba(45,187,106,0.14)', borderRadius: 999,
            padding: '1px 6px', fontSize: 11, fontWeight: 700,
          }}>+1</span>
        </button>
      </div>
      {(ready.length > 0 || pendingCount > 0) ? (
        <ul aria-label="Variaciones" style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(72px, 1fr))',
          gap: 8, padding: 0, listStyle: 'none', margin: 0,
        }}>
          {ready.map((v) => (
            <li key={v.id}>
              <button
                type="button"
                aria-pressed={active?.id === v.id}
                onClick={() => onSelectVariation?.(v.id)}
                style={{
                  width: '100%', aspectRatio: '3/4', padding: 0,
                  border: active?.id === v.id ? '3px solid #2DBB6A' : '1px solid #e6e0d4',
                  borderRadius: 8, overflow: 'hidden', cursor: 'pointer',
                  background: '#f4ede0',
                }}
              >
                <img src={v.url} alt={`Variación ${v.id}`}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              </button>
            </li>
          ))}
          {Array.from({ length: pendingCount }, (_, i) => (
            <li key={`pending-${i}`}>
              <div role="status" aria-label="Variación en generación"
                style={{
                  width: '100%', aspectRatio: '3/4',
                  border: '1px solid #e6e0d4', borderRadius: 8,
                  background: '#f4ede0',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}
              >
                <ThumbSpinner size={18} />
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p style={{ fontSize: 12, color: 'var(--ravit-text-muted, #999)' }}>
          Aún no se ha generado una variación. Vuelve a Cara y pulsa Generar.
        </p>
      )}
    </div>
  );
}


function ThumbSpinner({ size = 18 }) {
  return (
    <span
      style={{ position: 'relative', width: size, height: size, display: 'inline-block' }}
      role="status"
    >
      <style>{`@keyframes wpSpin{to{transform:rotate(360deg)}}`}</style>
      <span style={{
        position: 'absolute', inset: 0,
        border: '2px solid transparent', borderTopColor: '#2DBB6A',
        borderRadius: '50%',
        animation: 'wpSpin 1.1s linear infinite',
      }} />
      <span style={{
        position: 'absolute', inset: '20%',
        border: '2px solid transparent', borderRightColor: '#2DBB6A',
        borderRadius: '50%',
        animation: 'wpSpin 0.8s linear infinite reverse',
      }} />
    </span>
  );
}
