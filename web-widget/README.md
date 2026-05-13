# CopilotoIA Web Widget — Distribución CDN (TASK-0070)

Paquete que produce el bundle `widget.js` + `widget.css` embebibles por cualquier sitio. Se publica en `s3://copilotoia-cdn/widget/v1/`.

## Instalar y construir

```bash
cd web-widget
npm install
npm run build      # genera dist/widget.js y dist/widget.css
npm run size       # falla si gzip(widget.js) > 30KB o gzip(widget.css) > 5KB
npm run lint
npm test
```

## Snippet que se entrega al cliente pyme

```html
<script async
        src="https://cdn.copilotoia.com/widget/v1/widget.js"
        data-tenant="<tenant_slug>"
        data-widget-token="<widget_token>"
        data-api-base="https://api.copilotoia.com"
        data-color="#1f7ae0"
        data-greeting="¿En qué te ayudamos?"
        data-logo="https://cdn.copilotoia.com/tenants/<slug>/logo.png"
        data-welcome="Atendemos de lunes a viernes."
        data-position="right"></script>
```

Los valores de `data-*` los devuelve `GET /v1/tenants/{tenant_id}/channels/web` (ya existe) y los inserta el snippet builder del backend. `data-api-base` es **obligatorio**: el host del CDN sólo sirve assets estáticos (no proxy de `/v1/web/chat/*`), así que el widget debe saber cuál es el origen real del API; el backend lo lee de la setting `web_widget_api_base`. El widget también carga su propia hoja de estilos (`widget.css`) desde el mismo path del script, inyectando un `<link rel="stylesheet">` en runtime — no hace falta pegarla aparte.

## Endpoints consumidos

| Endpoint                                          | Cuándo                              |
|---------------------------------------------------|-------------------------------------|
| `POST /v1/web/chat/start`                         | Al enviar el formulario lead-capture|
| `POST /v1/web/chat/{conversation_id}/messages`    | En cada turno del usuario           |
| `GET  /v1/web/chat/{conversation_id}/messages`    | Polling cada 3s tras el primer turno|

## Publicación

`.github/workflows/web-widget.yml` corre en cada push/PR (build + lint + size + tests). El job de despliegue se dispara con un release `widget-vX.Y.Z` o `workflow_dispatch` y publica:

```
s3://copilotoia-cdn/widget/v1/widget.js
s3://copilotoia-cdn/widget/v1/widget.css
```

Con `Cache-Control: public, max-age=300` para hot-fix rápidos y un alias inmutable `widget.<sha>.js` cacheable a 1 año.
