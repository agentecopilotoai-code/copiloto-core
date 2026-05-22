/**
 * UI-INFLU-014.1 — WizardPreview persistente para los 5 steps.
 *
 * Vive en la columna izquierda del wizard (ver `WizardLayout`). Siempre
 * visible mientras el usuario edita Cara → Cuerpo → Identidad → Voz →
 * Plataformas. La generación es paralela al wizard: el usuario puede
 * apretar "Generar +1" en cualquier paso y ver las thumbnails crecer
 * abajo del preview grande mientras sigue editando.
 *
 * Props:
 *   personaName       — string opcional que se muestra como overlay
 *                       ("Personaje en construcción" si no hay).
 *   generationNumber  — int para el overlay "GENERACIÓN #NN".
 *   variations        — array de { id, url, status, marked_canonical }.
 *                       status puede ser 'pending' (spinner) | 'ready' (img).
 *   selectedIndex     — int idx de la variación que se muestra en el
 *                       preview grande. Null si no hay ninguna ready.
 *   onSelectVariation — (idx) => void; click en thumbnail.
 *   onGenerate        — () => void; click en "Generar +1".
 *   pendingCount      — int de placeholders con spinner adicionales
 *                       (optimistic UI mientras el backend procesa).
 *   creditCost        — int (default 1) que se muestra en el botón.
 *   disabled          — bloquea el botón mientras hay un POST en vuelo.
 */
import styles from './WizardPreview.module.css';

const PREVIEW_PLACEHOLDER = '/admin/assets/persona-placeholder.svg';

export function WizardPreview({
  personaName = 'Personaje en construcción',
  generationNumber = 1,
  variations = [],
  selectedIndex = null,
  onSelectVariation,
  onGenerate,
  pendingCount = 0,
  creditCost = 1,
  disabled = false,
}) {
  // Determinar la variación a mostrar en el preview grande:
  // 1) selectedIndex explícito → esa.
  // 2) Sin selectedIndex pero hay variations ready → la última (auto-select).
  // 3) Sin variations → placeholder con spinner si pendingCount > 0.
  const readyVariations = variations.filter((v) => v?.status !== 'pending' && v?.url);
  const fallbackIndex = readyVariations.length > 0
    ? variations.indexOf(readyVariations[readyVariations.length - 1])
    : null;
  const activeIndex = selectedIndex != null && variations[selectedIndex]?.url
    ? selectedIndex
    : fallbackIndex;
  const active = activeIndex != null ? variations[activeIndex] : null;
  const isEmpty = !active && pendingCount === 0;

  const thumbnails = [
    ...variations,
    // Placeholders pending para optimistic UI (el thumbnail aparece con
    // spinner inmediato al apretar Generar; cuando el polling trae la
    // URL real, el item se reemplaza).
    ...Array.from({ length: pendingCount }, (_, i) => ({
      id: `__pending-${i}`,
      status: 'pending',
      url: null,
    })),
  ];

  return (
    <div className={styles.root} data-component="WizardPreview">
      {/* Preview grande */}
      <div className={styles.previewFrame}>
        <span className={styles.previewBadge} aria-hidden="true">
          <span className={styles.previewBadgeDot} /> VISTA PREVIA
        </span>
        {active ? (
          <img
            className={styles.previewImg}
            src={active.url}
            alt={`Variación ${activeIndex + 1} de ${personaName}`}
          />
        ) : (
          <div className={styles.previewEmpty} aria-live="polite">
            {pendingCount > 0 ? (
              <Spinner size="md" label="Generando primera variación…" />
            ) : (
              <p className={styles.previewEmptyHint}>
                Configura los rasgos y pulsa Generar.
              </p>
            )}
          </div>
        )}
        <div className={styles.previewMeta}>
          <div className={styles.previewMetaLabel}>
            GENERACIÓN #{String(generationNumber).padStart(2, '0')}
          </div>
          <div className={styles.previewMetaName}>{personaName}</div>
        </div>
      </div>

      {/* Tira de thumbnails + botón Generar */}
      <div className={styles.tray}>
        <div className={styles.trayHead}>
          <span className={styles.trayLabel}>Variaciones generadas</span>
          <button
            type="button"
            className={styles.generateBtn}
            onClick={onGenerate}
            disabled={disabled}
            aria-label={`Generar nueva variación, cuesta ${creditCost} crédito`}
          >
            <span className={styles.generateIcon} aria-hidden="true">✦</span>
            <span>Generar</span>
            <span className={styles.generateCost} aria-hidden="true">+{creditCost}</span>
          </button>
        </div>
        {thumbnails.length === 0 ? (
          <p className={styles.trayEmpty}>
            Aún no has generado ninguna variación.
          </p>
        ) : (
          <ul className={styles.thumbList} role="list">
            {thumbnails.map((v, idx) => {
              const isActive = idx === activeIndex;
              const isPending = v?.status === 'pending' || !v?.url;
              return (
                <li key={v.id ?? idx} className={styles.thumbItem}>
                  <button
                    type="button"
                    className={[
                      styles.thumbBtn,
                      isActive ? styles['thumbBtn--active'] : '',
                    ].filter(Boolean).join(' ')}
                    onClick={() => !isPending && onSelectVariation?.(idx)}
                    disabled={isPending}
                    aria-pressed={isActive}
                    aria-label={
                      isPending
                        ? 'Variación en generación'
                        : `Seleccionar variación ${idx + 1}`
                    }
                  >
                    {isPending ? (
                      <span className={styles.thumbSpinnerWrap}>
                        <Spinner size="sm" />
                      </span>
                    ) : (
                      <img
                        className={styles.thumbImg}
                        src={v.url}
                        alt={`Variación ${idx + 1}`}
                      />
                    )}
                    {isActive && !isPending ? (
                      <span className={styles.thumbCheck} aria-hidden="true">✓</span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}


/**
 * Spinner — círculos concéntricos pequeños y centrados, estilo del
 * diseño del PNG enviado por el usuario (no un spinner CSS dominante).
 */
function Spinner({ size = 'sm', label = null }) {
  const px = size === 'md' ? 28 : 16;
  return (
    <span
      className={styles.spinner}
      role="status"
      aria-label={label || 'Cargando'}
      style={{ width: px, height: px }}
    >
      <span className={styles.spinnerRing1} />
      <span className={styles.spinnerRing2} />
      {label ? <span className={styles.spinnerLabel}>{label}</span> : null}
    </span>
  );
}
