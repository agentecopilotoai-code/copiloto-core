/**
 * UI-INFLU-003 — Empty state del Casting del módulo Influencer.
 *
 * Se renderiza cuando `GET /v1/influencer/casting` devuelve `personas=[]`.
 * Reusa la primitiva `EmptyState` (UI-001) + estilos compartidos del módulo
 * (`_shared/RavitStyles.module.css`).
 *
 * Permission gate: la CTA "Crear personaje" renderiza siempre; queda
 * deshabilitada (con tooltip) si el rol no tiene `influencer.personas.write`.
 */
import { useNavigate, useParams } from 'react-router-dom';

import { usePermissions } from '../../../permissions/index.js';
import styles from '../_shared/RavitStyles.module.css';


function CastingEmptyIllustration() {
  return (
    <svg
      viewBox="0 0 200 200"
      width="160"
      height="160"
      role="img"
      aria-label="Casting vacío"
      style={{ marginBottom: 16 }}
    >
      {/* Spotlight cream */}
      <circle cx="100" cy="100" r="80" fill="#F1EDE3" />
      <circle cx="100" cy="100" r="60" fill="#FBF9F2" />
      {/* Empty chair / placeholder figure */}
      <path
        d="M70 110 L70 140 L130 140 L130 110 Q130 90 100 90 Q70 90 70 110 Z"
        fill="none"
        stroke="#2DBB6A"
        strokeWidth="2.5"
        strokeDasharray="6,4"
        strokeLinejoin="round"
      />
      <circle cx="100" cy="70" r="14" fill="none" stroke="#2DBB6A" strokeWidth="2.5" strokeDasharray="4,3" />
      {/* Plus sign in the middle */}
      <g transform="translate(100, 100)">
        <circle r="12" fill="#2DBB6A" />
        <path d="M-6 0 H 6 M 0 -6 V 6" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" />
      </g>
    </svg>
  );
}


export function CastingEmptyState() {
  const navigate = useNavigate();
  const { tenantSlug } = useParams();
  const { can } = usePermissions();
  const canWrite = can('influencer.personas.write');

  const handleCreate = () => {
    navigate(`/t/${tenantSlug}/influencer/personas/new/step-1`);
  };

  return (
    <div className={styles.page} data-module="influencer" data-view="casting-empty">
      <div className={styles.pageHeader}>
        <div className={styles.eyebrow}>Ravit Studio · Casting</div>
        <h1 className={styles.h1Page}>Tu casting está vacío</h1>
        <p className={styles.textSubtle}>
          Crea tu primer personaje virtual para empezar a generar contenido con su voz.
        </p>
      </div>

      <div className={styles.cardElevated} style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        padding: '64px 32px',
        maxWidth: 640,
        marginInline: 'auto',
      }}>
        <CastingEmptyIllustration />
        <h2 className={styles.h2Section}>Aún no tienes personajes</h2>
        <p className={styles.textSubtle} style={{ maxWidth: 440, margin: '0 0 24px' }}>
          Cada personaje será la cara de tu marca en posts, reels y anuncios.
          El wizard de 5 pasos te lleva de la mano.
        </p>
        <button
          type="button"
          className={styles.btnPrimaryLg}
          disabled={!canWrite}
          onClick={canWrite ? handleCreate : undefined}
          title={
            canWrite
              ? undefined
              : 'No tienes permiso para crear personajes (solo Manager/Admin/Owner)'
          }
        >
          Crear personaje
        </button>
      </div>
    </div>
  );
}
