/**
 * UI-INFLU-016-FU — Ilustraciones SVG para el landing público Ravit Studio.
 *
 * Cada SVG es un componente React independiente, escalable (no PNG) y usa
 * tokens del design system (var(--ra-*)). El logo principal `RavitMark`
 * replica el thumbnail oficial del HTML `Ravit Studio Landing _standalone_.html`.
 */


/**
 * RavitMark — logo oficial. Mancha verde con highlight blanco + arco de
 * sombra interior. Replica el SVG del thumbnail del HTML standalone.
 */
export function RavitMark({ size = 56, withText = false }) {
  return (
    <svg
      viewBox="0 0 240 240"
      width={size}
      height={withText ? size * 1.5 : size}
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Ravit Studio"
    >
      <g transform="translate(40, 28)">
        <path
          d="M80 16 C 120 28, 140 60, 128 100 C 116 132, 76 144, 44 128 C 12 112, 8 72, 28 48 C 44 28, 64 20, 80 16 Z"
          fill="#2DBB6A"
        />
        <circle cx="88" cy="56" r="7" fill="#FFFFFF" />
        <path
          d="M44 128 C 60 100, 76 76, 100 56"
          stroke="#0F7A3F"
          strokeWidth="3"
          fill="none"
          opacity="0.4"
        />
      </g>
      {withText && (
        <text
          x="120"
          y="220"
          textAnchor="middle"
          fontFamily="'Geist', system-ui, sans-serif"
          fontSize="32"
          fontWeight="700"
          letterSpacing="-0.02em"
          fill="#1B2542"
        >
          Ravit Studio
        </text>
      )}
    </svg>
  );
}


/**
 * HeroIllustration — mockup ilustrativo del producto: avatar del personaje
 * + feed mockeado a su lado. Va en el hero como complemento visual al
 * headline.
 */
export function HeroIllustration() {
  return (
    <svg
      viewBox="0 0 520 480"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="Ilustración: personaje virtual con su feed de redes sociales"
      style={{ width: '100%', height: 'auto', maxWidth: 520 }}
    >
      {/* Background card */}
      <rect x="20" y="20" width="480" height="440" rx="24" fill="#fff" stroke="rgba(15,122,63,0.08)" />

      {/* Avatar circle */}
      <circle cx="170" cy="170" r="100" fill="#F1EDE3" />
      <path
        d="M120 170 c 0 -33 22 -60 50 -60 s 50 27 50 60 v 80 h -100 z"
        fill="#0F7A3F"
      />
      <circle cx="170" cy="135" r="36" fill="#E8C9A9" />
      {/* Hair */}
      <path d="M134 115 q 36 -40 72 0 q -10 -10 -36 -10 q -26 0 -36 10 z" fill="#1B2542" />
      {/* Eyes */}
      <circle cx="158" cy="138" r="3" fill="#1B2542" />
      <circle cx="184" cy="138" r="3" fill="#1B2542" />
      {/* Smile */}
      <path d="M158 152 q 12 8 24 0" stroke="#1B2542" strokeWidth="2" fill="none" strokeLinecap="round" />

      {/* Verified badge */}
      <circle cx="218" cy="218" r="14" fill="#2DBB6A" stroke="#fff" strokeWidth="3" />
      <path d="M212 218 l 4 4 l 8 -8" stroke="#fff" strokeWidth="2.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />

      {/* Persona name */}
      <text x="170" y="300" textAnchor="middle" fontFamily="'Geist', system-ui, sans-serif" fontSize="18" fontWeight="700" fill="#1B2542">
        Sofía Vega
      </text>
      <text x="170" y="320" textAnchor="middle" fontFamily="'Geist', system-ui, sans-serif" fontSize="12" fill="#6b7280">
        @sofia.studio · 124K seguidores
      </text>

      {/* Mock posts grid */}
      <g transform="translate(310, 60)">
        {/* row 1 */}
        <rect x="0" y="0" width="60" height="60" rx="8" fill="#0F7A3F" opacity="0.85" />
        <circle cx="30" cy="30" r="14" fill="#E8C9A9" />
        <rect x="70" y="0" width="60" height="60" rx="8" fill="#2DBB6A" opacity="0.85" />
        <circle cx="100" cy="30" r="14" fill="#E8C9A9" />
        <rect x="140" y="0" width="60" height="60" rx="8" fill="#F1EDE3" stroke="#1B2542" strokeOpacity="0.1" />
        <text x="170" y="35" textAnchor="middle" fontFamily="'Geist', sans-serif" fontSize="20" fill="#1B2542">+12</text>

        {/* row 2 */}
        <rect x="0" y="70" width="60" height="60" rx="8" fill="#1B2542" opacity="0.9" />
        <rect x="14" y="86" width="32" height="28" rx="4" fill="#2DBB6A" />
        <rect x="70" y="70" width="60" height="60" rx="8" fill="#0F7A3F" opacity="0.7" />
        <circle cx="100" cy="100" r="14" fill="#E8C9A9" />
        <rect x="140" y="70" width="60" height="60" rx="8" fill="#2DBB6A" opacity="0.65" />
        <circle cx="170" cy="100" r="14" fill="#E8C9A9" />

        {/* row 3 — engagement bar */}
        <rect x="0" y="150" width="200" height="60" rx="12" fill="#F1EDE3" />
        <text x="14" y="172" fontFamily="'Geist', sans-serif" fontSize="11" fill="#6b7280">
          Engagement esta semana
        </text>
        <text x="14" y="195" fontFamily="'Geist', sans-serif" fontSize="22" fontWeight="700" fill="#0F7A3F">
          +8.4%
        </text>
        <text x="100" y="195" fontFamily="'Geist', sans-serif" fontSize="11" fill="#2DBB6A">
          ↑ vs semana previa
        </text>

        {/* row 4 — schedule mini */}
        <rect x="0" y="220" width="200" height="64" rx="12" fill="#1B2542" />
        <text x="14" y="242" fontFamily="'Geist', sans-serif" fontSize="10" fill="rgba(255,255,255,0.6)">
          PRÓXIMO POST
        </text>
        <text x="14" y="262" fontFamily="'Geist', sans-serif" fontSize="14" fontWeight="600" fill="#fff">
          Reel · 11:00 mañana
        </text>
        <text x="14" y="278" fontFamily="'Geist', sans-serif" fontSize="11" fill="rgba(255,255,255,0.7)">
          Instagram · TikTok
        </text>
      </g>
    </svg>
  );
}


/**
 * IconCircle — círculo pequeño con un emoji-style SVG icon centrado.
 * Usado en los pasos "Cómo funciona".
 */
function IconCircle({ children, color = '#0F7A3F' }) {
  return (
    <div
      aria-hidden="true"
      style={{
        width: 56, height: 56, borderRadius: 14,
        background: color,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        flexShrink: 0,
        boxShadow: '0 4px 12px rgba(15,122,63,0.18)',
      }}
    >
      {children}
    </div>
  );
}


export function CastingIcon() {
  return (
    <IconCircle>
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21 c 0 -4 4 -7 8 -7 s 8 3 8 7" />
      </svg>
    </IconCircle>
  );
}


export function GenerateIcon() {
  return (
    <IconCircle color="#2DBB6A">
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 5 h 14 v 14 h -14 z" />
        <circle cx="9" cy="10" r="2" />
        <path d="M5 17 l 5 -5 l 4 4 l 5 -5" />
      </svg>
    </IconCircle>
  );
}


export function ScheduleIcon() {
  return (
    <IconCircle>
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M3 9 h 18" />
        <path d="M8 3 v 4 M16 3 v 4" />
      </svg>
    </IconCircle>
  );
}


export function MonetizeIcon() {
  return (
    <IconCircle color="#2DBB6A">
      <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 6 v 12 M9 9 h 5 a 2 2 0 0 1 0 4 h -4 a 2 2 0 0 0 0 4 h 5" />
      </svg>
    </IconCircle>
  );
}


/**
 * PersonaAvatar — avatar abstracto reutilizable con paleta de skin tones
 * para los "ejemplos" de personajes en la grilla de casting.
 */
export function PersonaAvatar({ name, handle, skin = '#E8C9A9', hair = '#1B2542', accent = '#2DBB6A' }) {
  return (
    <svg viewBox="0 0 220 240" xmlns="http://www.w3.org/2000/svg"
         role="img" aria-label={`Personaje ${name}`} style={{ width: '100%', height: 'auto' }}>
      <rect width="220" height="240" rx="16" fill="#F1EDE3" />
      {/* Body */}
      <path d="M55 200 c 0 -30 25 -55 55 -55 s 55 25 55 55 v 40 h -110 z" fill={accent} />
      {/* Head */}
      <circle cx="110" cy="100" r="40" fill={skin} />
      <path d="M70 75 q 40 -45 80 0 q -10 -12 -40 -12 q -30 0 -40 12 z" fill={hair} />
      <circle cx="96" cy="103" r="3" fill="#1B2542" />
      <circle cx="124" cy="103" r="3" fill="#1B2542" />
      <path d="M98 118 q 12 8 24 0" stroke="#1B2542" strokeWidth="2" fill="none" strokeLinecap="round" />
      {/* Name */}
      <text x="110" y="200" textAnchor="middle" fontFamily="'Geist', sans-serif" fontSize="16" fontWeight="700" fill="#fff">
        {name}
      </text>
      <text x="110" y="220" textAnchor="middle" fontFamily="'Geist', sans-serif" fontSize="11" fill="rgba(255,255,255,0.8)">
        {handle}
      </text>
    </svg>
  );
}
