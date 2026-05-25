# Flujo desde cero — Módulo Gestión Documental (GD)

> **A quién va dirigido:** platform_owner o admin del tenant que acaba de
> activar el módulo GD y no sabe qué pasos seguir.
> **Tiempo estimado:** 20–40 min (sin contar la carga real de TRD, que es
> ejercicio del archivista).

Cuando un tenant activa el módulo GD por primera vez, las tablas del schema
`gd.*` están vacías (excepto los catálogos seedeados: roles, permisos y la
matriz rol×permiso). Este documento describe el orden en que las pantallas
deben usarse para que el módulo quede operativo.

---

## 1) Activación del módulo (lo hace el platform_owner)

Pre-requisito: el platform_owner ya ejecutó:

```bash
./scripts/bootstrap.sh --module=gd        # carga schema + seed
```

o ya pasó por la vista de creación de tenant con el switch "Gestión
Documental" activo, lo cual ejecuta `bootstrap_gd_for_tenant()`. Esto:

- Activa el módulo en `app.tenant_modules` (`gestion_documental=true`).
- Inserta los 19 roles del sistema en `gd.rol` (catálogo).
- Inserta los 119 permisos en `gd.permiso`.
- Inserta las ~582 filas de la matriz rol×permiso (`gd.rol_permiso`).
- Asigna automáticamente `gd.admin_sistema` con alcance `global` a TODOS
  los usuarios que ya son `owner` o `admin` del tenant.

**Verificación rápida:**

```bash
curl -H "Cookie: $cookie" $BASE/api/v1/gd/me
# debe devolver roles_gd_vigentes con al menos "gd.admin_sistema"
```

Si `roles_gd_vigentes` viene vacío, el usuario NO es `owner`/`admin`
del tenant. Solución: asignar uno de esos roles desde la pantalla de
administración del tenant ANTES de entrar al módulo.

---

## 2) Primera versión de la estructura orgánica  ⚠️ paso bloqueante

Sin una versión vigente de estructura orgánica, **NO se puede crear
ninguna dependencia**, lo que implica que tampoco se pueden crear
usuarios, ni asignar PQRSD, ni clasificar radicados. Es el primer
paso operativo obligatorio.

**Cómo:**

1. Entrá a `/gd/admin/estructura`.
2. La pantalla muestra el empty state "Aún no hay estructura orgánica"
   con el CTA "+ Crear primera versión".
3. Llená el modal:
   - **Número de versión** (requerido) — usá el número del acto
     administrativo que aprueba la estructura (ej. `Decreto 001 de 2026`)
     o un identificador interno (`v1`, `2026`).
   - **Acto administrativo** (recomendado) — el documento que da soporte
     legal a la estructura.
   - **Descripción** (opcional) — qué cambia respecto a la versión
     anterior (en la primera versión podés dejarla en blanco).
   - **Fecha de inicio de vigencia** (requerido) — por defecto hoy.
4. "Crear versión". El backend devuelve `version_estructura_id`, que
   queda disponible en `getEstructuraOrganica()` para el resto del
   flujo.

> **Nota:** versionar la estructura más adelante (ej. ante una
> reorganización institucional) sigue el mismo flujo, pero el CTA aparece
> como "Nueva versión" en la barra de acciones, no como botón primario
> del empty state.

---

## 3) Cargar dependencias raíz + sub-dependencias

1. Misma pantalla `/gd/admin/estructura`, ahora con CTA
   "+ Nueva dependencia raíz" habilitado.
2. Por cada nivel del organigrama:
   - **Código orgánico** — identificador alineado al organigrama oficial
     (`1000` para despacho, `1100` para secretaría general, etc.).
   - **Nombre** — denominación oficial.
   - **Fecha de inicio de vigencia** — generalmente igual a la fecha de
     la versión.
3. Para crear hijas, usá el botón "+ Hija" sobre el nodo padre.

**Orden recomendado:**
- Despacho → Secretarías → Subsecretarías → Oficinas → Grupos.

---

## 4) Crear perfiles de usuario GD

Sin perfil GD, un usuario del tenant NO puede entrar al módulo (recibe
404 de `/v1/gd/me`).

1. `/gd/admin/usuarios` → "Nuevo perfil".
2. Asociar al `user_id` del usuario en el tenant (autocompletado).
3. Seleccionar **dependencia primaria** (ya creada en el paso anterior).
4. El perfil entra en estado `activo` por default.

---

## 5) Asignar roles GD a cada perfil

1. Desde el detalle del perfil, "Asignar rol".
2. Elegir uno de los 19 roles del catálogo + alcance:
   - `global` — toda la institución (reservado a admin_sistema).
   - `institucional` — operación en toda la institución.
   - `dependencia` — solo su dependencia primaria.
   - `propio` — solo lo que él generó.
3. Repetir si el usuario tiene roles múltiples (ej. profesional +
   firmante).

> **Tip:** el sidebar y header del módulo muestran el rol "más fuerte"
> automáticamente (admin > operativo > consulta). Si el usuario tiene
> varios, hover sobre el chip muestra la lista completa.

---

## 6) Configurar parámetros institucionales

`/gd/admin/parametros` — al menos:

- `vu.formato_radicado` — patrón de numeración (`{anio}-{consecutivo:08d}`).
- `pqrsd.dias_habiles_por_tipo` — términos legales por tipo de PQRSD
  (ej. peticiones: 15, quejas: 15, consultas: 30).
- `firma.algoritmo_default` — `RS256` (recomendado).

---

## 7) Configurar calendario laboral

`/gd/admin/calendario` — cargar los días festivos del año:

- Festivos nacionales colombianos (Ley 51 de 1983).
- Días no laborables locales (acuerdos del tenant).

Sin esto, el cálculo de vencimientos de PQRSD usa solo
sábados/domingos como no laborales.

---

## 8) Cargar TRD (Tabla de Retención Documental)

`/gd/trd/series` — este es un ejercicio archivístico, **no técnico**:

1. Crear series documentales (nivel 1).
2. Crear subseries (nivel 2).
3. Crear tipos documentales (nivel 3).
4. Asociar cada tipo a una serie/subserie.
5. Asignar la TRD a cada dependencia (la dependencia hereda las series
   que le aplican).

> En tenants reales, este paso lo ejecuta el archivista con apoyo del
> admin_sistema. Para QA/dev hay un seed mínimo en
> `scripts/dev/seed_gd_demo.py`.

---

## 9) Configurar plantillas y firmas

- `/gd/admin/plantillas` — al menos una plantilla por tipo documental
  que se generará automáticamente (oficio_respuesta, memorando_interno,
  constancia_radicacion, etc.).
- `/gd/admin/firmas` — registrar los firmantes autorizados (rol
  `gd.firmante`) + cargar sus certificados.

---

## 10) Activar periféricos (opcional)

Si la entidad opera con scanners de mesa o impresoras térmicas en la
ventanilla:

- `/gd/admin/perifericos` → "Nuevo periférico".
- Tipo + serial + ubicación + dirección de red.

---

## 11) Validar flujo end-to-end

Pequeño smoke test antes de declarar "operativo":

1. Como `gd.radicador`, crear un radicado de entrada en
   `/gd/ventanilla/nuevo`.
2. Como `gd.admin_pqrsd`, asignarlo en `/gd/pqrsd`.
3. Como `gd.profesional`, ver el ítem en `/gd/buzon` y proyectar
   respuesta en `/gd/pqrsd/mias`.
4. Como `gd.jefe_dependencia`, aprobar en `/gd/correspondencia/aprobar`.
5. Como `gd.firmante`, firmar en `/gd/firmas/por-firmar`.
6. Como `gd.auditor`, ver la cadena de eventos en `/gd/auditoria`.

Si los 6 pasos completan sin error 403/404/422, el módulo está
operativo end-to-end.

---

## Anti-patrones comunes (cosas que NO deberías hacer)

1. ❌ **Crear dependencias antes que la versión** — el form devuelve
   422; ahora el botón está deshabilitado para prevenirlo.
2. ❌ **Asignar `gd.admin_sistema` con alcance `dependencia`** — pierde
   permisos institucionales. Siempre con alcance `global` o
   `institucional`.
3. ❌ **Olvidar el calendario laboral** — los vencimientos de PQRSD se
   calcularán con sábados/domingos solamente y violarán los términos
   legales reales.
4. ❌ **No configurar series TRD** — toda clasificación documental falla;
   los radicados quedan en limbo.
5. ❌ **Crear usuarios sin dependencia primaria** — varias pantallas
   (buzón, mis PQRSD, etc.) requieren dependencia para resolver
   alcance.

---

## Referencias

- Catálogo de roles: `app/gd/bootstrap.py::_GD_SYSTEM_ROLES`
- Matriz rol×permiso: `app/gd/bootstrap.py::_GD_MATRIZ_ROL_MODULO`
- Permisos UI: `docs/gestion documental/MATRIZ_PERMISOS.md`
- Backlog UI completo: `docs/gestion documental/UI_BACKLOG.md`
- API completa: `docs/gestion documental/integracion/`
