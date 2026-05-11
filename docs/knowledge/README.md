# Knowledge base — Plantillas por tipo de negocio

Esta carpeta contiene **plantillas completas de base de conocimiento** organizadas por
tipo de negocio. Cada subcarpeta es un set listo para subirse al Knowledge Studio del
admin-panel y dejar al asistente operando correctamente desde el primer día.

## Subcarpetas disponibles

| Carpeta | Tipo de negocio | Idioma |
|---------|----------------|--------|
| [`peluqueria/`](peluqueria/) | Salón de belleza con servicios de peluquería, manicuria y pedicura | Español (Colombia) |
| [`consultorio-medicina-estetica/`](consultorio-medicina-estetica/) | Consultorio de medicina estética: inyectables, láser, corporales, dermatología estética | Español (Colombia) |
| [`clinica-dental/`](clinica-dental/) | Clínica odontológica integral: general, especialidades, ortodoncia, implantes | Español (Colombia) |

## Documentos típicos por tipo

Cada subcarpeta incluye, como mínimo:

- `bienvenida-presentacion.md` — identidad, qué ofrece, tono y límites del asistente.
- `horarios-atencion.md` — horario regular, disponibilidad por servicio, cierres especiales.
- `proceso-agendamiento.md` — flujo paso a paso del agendamiento vía WhatsApp.
- `politica-reservas-cancelacion.md` — anticipos, cancelaciones, reagendamientos, llegadas tarde, pagos.
- `preguntas-frecuentes.md` — preguntas frecuentes específicas del negocio.
- `atencion-quejas-escalamiento.md` — manejo de quejas, escalamiento a humano, opt-out, privacidad.
- `servicios-*.csv` — catálogo de servicios con precio referencial, duración y notas.
- `paquetes-combos.csv` — paquetes y combos cuando aplica.

Documentos específicos por tipo de negocio:

- **Medicina estética:** `contraindicaciones-y-seguridad.md`, `consentimiento-informado.md`.
- **Clínica dental:** `urgencias-dentales.md`, `politica-financiacion-planes-pago.md`.

## Cómo usar estas plantillas

1. Identifica el tipo de negocio del tenant.
2. Carga todos los archivos `.md` y `.csv` de la subcarpeta correspondiente al Knowledge
   Studio (admin-panel → módulo Knowledge).
3. Personaliza los placeholders entre corchetes (`[actualizar con dirección real]`,
   `[actualizar con ciudad]`, nombres de marca, etc.).
4. Ajusta precios, horarios y servicios reales del cliente.
5. Indexa los documentos y verifica con `evaluateIntent` y consultas RAG que el asistente
   responde correctamente.

## Notas para los tres sets

- Los precios son referenciales y en pesos colombianos (COP). Deben revisarse antes de salir
  a producción para cada cliente.
- Todos los documentos asumen WhatsApp como canal principal de atención.
- El asistente está diseñado para **no entregar diagnósticos clínicos ni recomendaciones
  médicas** en los sets clínicos (medicina estética y dental). Todo escala a profesional.
- Cumplimiento normativo aludido (Colombia): Ley 1581/2012 (datos personales), Resolución
  1995/1999 (historia clínica), Resolución 8430/1993 (consentimiento), Resolución 13437/1991
  (derechos del paciente), Ley 23/1981 (ética médica).

## Cómo extender este knowledge base

Si necesitas agregar un nuevo tipo de negocio (ej. spa, óptica, veterinaria, gimnasio,
estudio de tatuajes):

1. Crea una nueva subcarpeta con el slug del negocio.
2. Copia el set base de la carpeta más cercana al rubro (clínico vs no clínico).
3. Ajusta los documentos al lenguaje y necesidades del nuevo tipo de negocio.
4. Añade documentos específicos cuando el contexto lo requiera (ej. urgencias para clínicos,
   garantías para retail, política de mascotas para veterinarias).
5. Actualiza este README con la nueva entrada en la tabla.
