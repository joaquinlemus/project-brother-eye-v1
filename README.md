# Portal SDN - Heladería Leche de Cabra


> La empresa del caso (antes "XYZ") es la cadena **Heladería Leche de Cabra**. Los identificadores
> técnicos conservan `xyz` (`/opt/xyz`, `xyz-sdn-portal`, tag `portal-xyz`) para no romper lo ya desplegado.
Portal propio que aprovisiona y desaprovisiona sucursales de una red **DMVPN dual hub**
(IPsec IKEv2, OSPFv2/OSPFv3, IPv4 + IPv6) usando **Ansible** como única vía de configuración,
con **IPAM** propio, monitoreo en **Zabbix** y despliegue en **AWS**.

Proyecto 2026 — Posgrado en Redes de Computadoras.

## Arquitectura en una línea

Implementada (laboratorio, una EC2):
`Usuario → Caddy HTTPS → Next.js estático + FastAPI → PostgreSQL (cola de jobs) → worker → run-job.sh (Ansible) → WireGuard → routers EVE-NG / Zabbix`

Diseño de producción (documento técnico): ALB, ECS Fargate, RDS y SQS en lugar de la EC2 única.
Instalación del portal: `docs/runbooks/portal.md`.

El documento de arquitectura completo (decisiones, diagramas, API, IPAM, seguridad, costos,
roadmap) está en el documento técnico del proyecto; los ADR están en `docs/adr/`.

## Estructura

| Carpeta | Contenido |
| --- | --- |
| `frontend/` | Next.js 15 + React 19 + MUI 7 (TypeScript), export estático en `frontend/out` |
| `backend/` | FastAPI + worker, Python 3.12+, capas dominio / aplicación / infraestructura / API |
| `database/` | Migraciones SQL (PostgreSQL 16): 001 esquema, 002 portal del laboratorio, 003 conectividad |
| `deploy/` | `install.sh`, Caddyfile, servicios systemd, `portalctl` |
| `ansible/` | Inventario dinámico, roles, plantillas Jinja2, playbooks, pruebas de render |
| `infrastructure/terraform/` | Módulos y ambientes (`lab`, `prod`) |
| `docker/` | Imágenes de frontend, api, worker y runner Ansible |
| `.github/workflows/` | CI (lint, pruebas, render, plan) y despliegue |
| `docs/` | ADR, runbooks (portal, Zabbix, Ansible en la EC2, día cero de routers), guion de demo, informe |

## Probar en local

```bash
# Backend: dominio + API + worker contra PostgreSQL, con run-job.sh simulado
cd backend && pip install -e ".[dev]"
TEST_DATABASE_URL=postgresql://portal:portal@127.0.0.1/portal_test pytest -q

# Frontend (genera frontend/out)
cd frontend && npm ci && npm run build

# Plantillas Ansible (sin routers ni secretos)
cd ansible && ANSIBLE_CALLBACKS_ENABLED= ansible-playbook -i tests/render_inventory.yml tests/render.yml
diff -ru tests/golden tests/out

# Migraciones
DATABASE_URL=postgresql://... python -m app.cli migrate     # desde backend/
```

## Parámetros del equipo

| Parámetro | Valor |
| --- | --- |
| Cumpleaños | MM = 12, D = 28 → MMDD = 1228 |
| LAN del sitio s | `10.(28+s).0.0/24` y `2001:1228:s::/64` |
| Túneles nube Hub 1 | `192.168.5.0/25` (R1 = .1, router s = `192.168.5.s`) |
| Túneles nube Hub 2 | `192.168.5.128/25` (R2 = .132, router s = `192.168.5.(130+s)`) |
| Site ID máximo | 124 (`130 + s ≤ 254`; la regla de la LAN permitiría 225) |

Si cambian, se actualizan en **tres** lugares:

1. `ansible/inventories/group_vars/all/main.yml` → `team_birthday` y `dmvpn_clouds`
2. Backend → `TEAM_BIRTH_MONTH`, `TEAM_BIRTH_DAY` y `backend/app/domain/ipam/addressing.py` (túneles)
3. `database/migrations/001_init.sql` → pools `lan-v6`, `tunnel*` y el máximo de `site-ids`

## Estado verificado

| Componente | Verificación |
| --- | --- |
| Esquema SQL | Aplica en PostgreSQL 16; la restricción `EXCLUDE` rechaza prefijos solapados |
| Backend | 23 pruebas (dominio, IPAM, máquina de estados, API, conectividad y retiro); ruff limpio |
| Frontend | `tsc` y `next build` sin errores |
| Ansible | `--syntax-check` de todos los playbooks; ansible-lint perfil `production`; render de plantillas igual a golden |
| Terraform | Escrito, **no validado** (`terraform validate` pendiente en CI) |
| Contra routers reales | Altas y bajas desde el portal en el laboratorio EVE-NG (R5, R13), con registro en Zabbix |

## Secretos

Nada sensible vive en el repositorio. En el laboratorio, los secretos de red (clave IKEv2,
SNMPv3, usuario de los routers, token de Zabbix) están en Ansible Vault en la EC2
(`ansible/inventories/group_vars/all/vault.yml`, ignorado por Git; ver `vault.yml.example`), y
los del portal en `/opt/xyz/portal/portal.env` (ver `deploy/portal.env.example`). En el diseño de
producción se guardan en AWS Secrets Manager.

El instalador (`deploy/install.sh`) necesita el frontend compilado: antes de copiar el código a
la EC2, ejecuta `cd frontend && npm ci && npm run build`.
