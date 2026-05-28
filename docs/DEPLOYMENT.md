# Deployment guide — llevar tu SaaS a producción

Esta guía cubre el deploy a producción de un proyecto generado con
`python -m copiloto_core new-project mi-saas --with-infra --prod-ready`
(v2.1.0+).

> Para el flow dev local, ver [QUICKSTART.md](QUICKSTART.md).
> Para configurar Auth0, ver [AUTH0.md](AUTH0.md).
> Para configurar email providers, ver [EMAIL.md](EMAIL.md).

---

## Filosofía

El core te entrega **3 caminos de deployment**, en orden de complejidad creciente:

| Camino | Cuándo | Costo aprox | Effort |
|--------|--------|-------------|--------|
| **A. VPS único (Docker Compose)** | 0-50k users, MVP, single region | $5-40/mes | 1-2h |
| **B. Cloud PaaS (Fly.io/Railway/Render)** | 0-100k users, sin DevOps | $25-100/mes | 30 min |
| **C. Orchestrator (k8s/ECS/Nomad)** | 100k+ users, multi-region, HA estricto | $200+/mes | varios días |

**No empieces por C**. Casi todos los SaaS exitosos viven en A o B por
años antes de necesitar k8s. La complejidad operativa de un cluster
te frena mucho más que la "limitación" de un VPS bien tuneado.

El `--prod-ready` del scaffolder optimiza para **camino A**. Lo que
genera (Dockerfile + compose.prod + gunicorn + nginx) sirve también
para B (los PaaS leen tu Dockerfile y se encargan del resto) y como
base para C (los manifiestos k8s reusan tu imagen).

---

## A. Deploy a VPS único con Docker Compose

### A.1 Preparar el VPS

Lo mínimo que necesitás en el VPS (Ubuntu 22.04/24.04, Debian 12):

```bash
# Como root o sudo
apt update && apt install -y docker.io docker-compose-v2 nginx certbot \
  python3-certbot-nginx ufw fail2ban

# Usuario dedicado para tu app (NO uses root)
adduser --system --group --shell /bin/bash --home /opt/{project} {project}
usermod -aG docker {project}

# Firewall: solo SSH + HTTP/HTTPS abiertos al mundo
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw enable
```

### A.2 Primer deploy

Desde tu máquina local (donde corriste `new-project`):

```bash
# 1. Generar secretos REALES de producción (NO los de dev)
cp .env.prod.example .env.prod
python -m copiloto_core generate-secrets --target=.env.prod
$EDITOR .env.prod   # editar AUTH0_*, S3 si usás S3 real, etc.

# 2. Copiar el código al VPS (puede ser git clone, scp, rsync…)
rsync -avz --exclude '.venv' --exclude '__pycache__' --exclude '.env' \
  ./ {user}@{vps}:/opt/{project}/

# 3. En el VPS, build + bootstrap + up
ssh {user}@{vps} 'cd /opt/{project} && \
  docker compose -f docker-compose.prod.yml build && \
  docker compose -f docker-compose.prod.yml --env-file .env.prod \
    run --rm app python -m copiloto_core bootstrap --create-app-user --no-seed && \
  docker compose -f docker-compose.prod.yml --env-file .env.prod \
    run --rm app python -m copiloto_core migrate --module={module} && \
  docker compose -f docker-compose.prod.yml --env-file .env.prod up -d'
```

> **Importante**: usá `--no-seed` en bootstrap de prod. El seed mete
> el tenant demo, que NO querés en producción.

### A.3 nginx + TLS

```bash
# En el VPS, copiar el template del scaffolder + editarlo
sudo cp /opt/{project}/nginx.conf.example /etc/nginx/sites-available/{project}.conf
sudo $EDITOR /etc/nginx/sites-available/{project}.conf   # reemplazar 'tudominio.com'
sudo ln -s /etc/nginx/sites-available/{project}.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# TLS gratis via Let's Encrypt
sudo certbot --nginx -d tudominio.com -d www.tudominio.com
# certbot inyecta los ssl_certificate paths automáticamente +
# configura cron de renewal.
```

Validar:
```bash
curl https://tudominio.com/v1/livez   # → {"status":"ok"}
curl https://tudominio.com/v1/readyz  # → {"ok":true,"checks":{...}}
```

### A.4 Configurar Auth0 para prod

Mismo flow de [AUTH0.md](AUTH0.md), pero contra un tenant **distinto**
al de dev. Configurá:
- Allowed Callback URLs: `https://tudominio.com/admin/callback`
- Allowed Logout URLs: `https://tudominio.com/`
- Allowed Web Origins: `https://tudominio.com`

> NUNCA reusés el tenant Auth0 de dev en prod — un MGMT token leaked
> de dev no debe poder tocar usuarios reales.

### A.5 Activar email providers en prod

Login como `platform_owner` en `https://tudominio.com/admin/platform/email-providers`
y configurá Resend/SendGrid/Mailgun/SMTP de **producción** (NO los de
sandbox). Ver [EMAIL.md](EMAIL.md) para los pasos detallados.

### A.6 Updates posteriores

Una vez deployado, los updates son:

```bash
# En tu máquina local, después de hacer cambios:
git push   # o rsync de nuevo

# En el VPS:
cd /opt/{project}
docker compose -f docker-compose.prod.yml build app
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  run --rm app python -m copiloto_core migrate --module={module}
docker compose -f docker-compose.prod.yml --env-file .env.prod \
  up -d --no-deps app   # solo recrea el app, no toca DB/Redis
```

O usá el workflow de GitHub Actions que vino con el scaffolder
(`.github/workflows/deploy.yml`) — configurá los secrets
(`DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_PATH`) y cada
push a `main` redeploya automáticamente.

---

## B. Deploy a Cloud PaaS

Los PaaS leen tu `Dockerfile` y se encargan del resto (TLS, scaling,
logs, etc.). El generador del core ya te dio el Dockerfile compatible.

### B.1 Fly.io

```bash
# Una vez (instalar flyctl)
brew install flyctl   # o https://fly.io/docs/hands-on/install-flyctl/

# En tu proyecto
fly launch              # detecta Dockerfile + te guía
fly secrets set AUTH0_DOMAIN=... DATABASE_URL=... [todas las del .env.prod]
fly postgres create     # provisiona Postgres managed
fly redis create        # provisiona Upstash Redis
fly deploy
```

> Fly te pide los healthchecks — apuntá a `/v1/readyz`. El period
> recomendado es 15s; timeout 5s.

### B.2 Railway

```bash
# UI-first: railway.app/new
# - Conectá tu repo
# - Add service: Postgres + Redis
# - Settings → Variables: pegá las de .env.prod
# - Settings → Healthcheck: /v1/readyz
```

Railway usa Buildpacks por default; forzá Dockerfile en Settings →
Build → "Use Dockerfile". El `gunicorn_conf.py` te da los workers
automáticos según los vCPUs del plan.

### B.3 Render

```bash
# render.com → New Web Service
# - Build Command: docker build .
# - Start Command: (vacío — usa el CMD del Dockerfile)
# - Health Check Path: /v1/readyz
```

Para Postgres + Redis, Render tiene servicios managed propios.

---

## C. Deploy a Kubernetes / orquestador

El scaffolder NO genera manifiestos k8s — el espacio de opciones es
demasiado amplio (Helm, Kustomize, Argo, raw YAML, distintas storage
classes, ingress controllers, etc.) para que un template default sea
útil sin asumir tu stack.

Lo que sí podés reusar:
- **La imagen del Dockerfile**: subila a tu registry (GHCR/ECR/GCR).
- **Las variables del `.env.prod.example`**: convertilas a `Secret`s
  + `ConfigMap`s.
- **Las probes `/v1/livez` + `/v1/readyz`**: cableá `livenessProbe` y
  `readinessProbe` del Deployment directo a esos paths.
- **Gunicorn config**: respetá `WEB_CONCURRENCY` env → el HPA scalea
  horizontal con más pods, no con más workers por pod.

Patrón típico de Deployment:

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: app
        image: ghcr.io/tuorg/{project}:v1.0.0
        env:
        - name: WEB_CONCURRENCY
          value: "4"
        envFrom:
        - secretRef:
            name: {project}-secrets
        - configMapRef:
            name: {project}-config
        livenessProbe:
          httpGet:
            path: /v1/livez
            port: 8000
          periodSeconds: 10
          failureThreshold: 3
        readinessProbe:
          httpGet:
            path: /v1/readyz
            port: 8000
          periodSeconds: 10
          failureThreshold: 3
        resources:
          limits: { memory: 1Gi, cpu: "1" }
          requests: { memory: 256Mi, cpu: 100m }
```

> Para Postgres + Redis en k8s, la práctica corriente es NO correrlos
> en el cluster. Usá RDS/CloudSQL/ElastiCache/Upstash — el costo
> operativo de mantener un Postgres HA en k8s no compensa salvo a
> escala XL.

---

## Backup automatizado

El scaffolder genera `scripts/backup.sh` que hace `pg_dump` con
rotación + integridad. Cableálo via systemd timer (mejor que cron):

```bash
# /etc/systemd/system/{project}-backup.service
[Unit]
Description={project} Postgres backup
[Service]
Type=oneshot
User={project}
WorkingDirectory=/opt/{project}
EnvironmentFile=/opt/{project}/.env.prod
ExecStart=/opt/{project}/scripts/backup.sh

# /etc/systemd/system/{project}-backup.timer
[Unit]
Description=Run {project}-backup daily at 03:00 UTC
[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true
[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now {project}-backup.timer
sudo systemctl list-timers | grep {project}   # verificar próximo fire
journalctl -u {project}-backup.service -f     # logs en vivo
```

Para off-site, setea `S3_BUCKET` en `.env.prod` y el script sube cada
dump a S3 (AWS, backblaze, minio remoto — cualquier compatible).

**Validá restores periódicamente** — un backup que nunca probaste no
es un backup. Cada trimestre, restaurá el último dump en un container
desechable y corré las migrations:

```bash
docker run --rm -v $(pwd):/dump -e PGPASSWORD=... pgvector/pgvector:pg16 \
  bash -c 'createdb -h xxx -U postgres test_restore && \
           pg_restore -h xxx -U postgres -d test_restore /dump/latest.dump'
```

---

## Observabilidad mínima

El core ya expone `/metrics` (Prometheus). Para verlo en un dashboard:

1. **Prometheus** scrape config:
   ```yaml
   - job_name: '{project}'
     scrape_interval: 30s
     static_configs:
       - targets: ['{project}.tudominio.com:443']
     scheme: https
     metrics_path: /metrics
     # Si /metrics está IP-allowlisted, scrapeá desde tu monitoring VPC.
   ```

2. **Grafana dashboard**: el core viene con un JSON pre-armado en
   [`copiloto_core/observability/dashboards/copiloto.json`](../copiloto_core/observability/dashboards/copiloto.json).
   Importalo en Grafana → Dashboards → Import → "Upload JSON file".

3. **Alertmanager rules**: en
   [`copiloto_core/observability/alerts/copiloto.yml`](../copiloto_core/observability/alerts/copiloto.yml).
   Pegalo en tu Prometheus + apuntá Alertmanager a Slack/PagerDuty.

Las alertas que ya están definidas:
- `BackendDown` — `/v1/readyz` falla por > 2 min
- `AuthSessionRevokeFailOpen` — fallback inseguro (M-002)
- `DispatcherCircuitOpen` — provider IA caído > 5 min
- `RateLimitHigh` — > 10% requests 429
- `DBPoolExhausted` — > 80% conexiones en uso

---

## Rotación de secretos

| Secret | Frecuencia | Cómo |
|--------|------------|------|
| `AUTH0_ADMIN_CLIENT_SECRET` | Cada 90d | Ver [runbooks/auth0_keys_rotation.md](runbooks/auth0_keys_rotation.md) |
| `SERVICE_TOKEN` | Cada 180d | Generar nuevo + redeploy (el viejo se invalida al primer request con el nuevo) |
| `SESSION_SECRET` | Solo si compromiso conocido | Rotación invalida TODAS las sesiones (logout forzado de todos los users) |
| `AI_PROVIDER_MASTER_KEY` | NUNCA sin migración | Si la rotás sin re-encriptar, perdés acceso a las API keys de AI + email guardadas en DB |
| `POSTGRES_PASSWORD` | Solo si compromiso conocido | `ALTER USER postgres WITH PASSWORD '...'` + actualizar `.env.prod` |
| `REDIS_PASSWORD` | Cada 365d | `CONFIG SET requirepass '...'` + actualizar `.env.prod` |
| Email provider API keys | Según política del proveedor | Editar desde `/admin/platform/email-providers` — no toca disk |

---

## Checklist pre-launch

Antes de abrir tu SaaS al público:

- [ ] DNS apuntando al VPS + propagado (verificar con `dig`)
- [ ] HTTPS funciona (`curl -I https://tudominio.com` → 200)
- [ ] `/v1/livez` y `/v1/readyz` ambos 200
- [ ] Auth0 tenant de **prod** (no dev) configurado + MFA Policy ON
- [ ] `.env.prod` con todos los CHANGE_ME reemplazados (incluído `AI_PROVIDER_MASTER_KEY`)
- [ ] `MFA_ENFORCEMENT_ENABLED=true`
- [ ] `bootstrap` corrido con `--no-seed` (sin tenant demo en prod)
- [ ] Backup automatizado configurado + tested un restore al menos una vez
- [ ] Email provider configurado desde `/admin/` + smoke test pasa
- [ ] Prometheus scrapeando `/metrics`
- [ ] Logs siendo enviados a algún destino persistente (no solo stdout del container)
- [ ] Firewall: solo 22/80/443 abiertos al mundo
- [ ] Usuario SSH dedicado (NO root); SSH key required (deshabilitar password auth)
- [ ] Tenants reales creados via `/admin/` (NO seed)
- [ ] Al menos 2 platform_owners definidos (single-person-of-failure es malo)
- [ ] Runbook de incidentes documentado para tu equipo

---

## Recursos relacionados

- [QUICKSTART.md](QUICKSTART.md) — flow dev local desde cero
- [AUTH0.md](AUTH0.md) — setup completo de Auth0 (dev + prod)
- [EMAIL.md](EMAIL.md) — multi-provider email + configuración en UI
- [CLI.md](CLI.md) — todos los comandos `python -m copiloto_core`
- [CONSUMER_ROUTES.md](CONSUMER_ROUTES.md) — mapa de URLs (quién sirve qué)
- [EXTENDING.md](EXTENDING.md) — escribir tu propio módulo opt-in
- [runbooks/auth0_keys_rotation.md](runbooks/auth0_keys_rotation.md) — rotación Auth0
