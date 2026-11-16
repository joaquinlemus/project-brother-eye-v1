#!/usr/bin/env bash
# Instala o actualiza el portal en la EC2 (misma máquina que Ansible).
#
#   cd xyz-sdn-portal && sudo PUBLIC_IP=<ip-elastica> ACME_EMAIL=<correo> bash deploy/install.sh
#
# Es idempotente: si ya está instalado, actualiza el código, aplica migraciones y reinicia.
# Conserva /opt/xyz/portal/portal.env, la base de datos y los usuarios.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "Ejecuta con sudo" >&2; exit 1; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE=/opt/xyz
P=$BASE/portal
RUN_USER="${PORTAL_USER:-$(stat -c %U "$BASE/ansible")}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
step() { printf '\n== %s\n' "$*"; }

[[ -d "$BASE/ansible" ]] || { echo "No existe $BASE/ansible: primero configura Ansible" >&2; exit 1; }
[[ -f "$SRC/frontend/out/index.html" ]] || { echo "Falta frontend/out (el zip trae el frontend compilado)" >&2; exit 1; }

# ---------------------------------------------------------------- IP pública
if [[ -z "${PUBLIC_IP:-}" ]]; then
  TOKEN=$(curl -s -m 3 -X PUT http://169.254.169.254/latest/api/token \
          -H "X-aws-ec2-metadata-token-ttl-seconds: 60" || true)
  PUBLIC_IP=$(curl -s -m 3 -H "X-aws-ec2-metadata-token: $TOKEN" \
          http://169.254.169.254/latest/meta-data/public-ipv4 || true)
fi
[[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "No pude detectar la IP pública; usa PUBLIC_IP=..." >&2; exit 1; }
echo "IP pública: $PUBLIC_IP  ·  usuario de servicio: $RUN_USER"

# ---------------------------------------------------------------- paquetes
step "Paquetes del sistema"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q postgresql python3-venv python3-dev libpq-dev build-essential curl gpg rsync
if ! command -v caddy >/dev/null; then
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt \
    > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -q
  apt-get install -y -q caddy
fi
caddy version

# ---------------------------------------------------------------- código
step "Código en $P"
install -d -o "$RUN_USER" -g "$RUN_USER" "$P" "$P/web" "$BASE/jobs"
rsync -a --delete --exclude '__pycache__' --exclude '.pytest_cache' --exclude 'tests' \
  "$SRC/backend/" "$P/backend/"
rsync -a --delete "$SRC/database/" "$P/database/"
rsync -a --delete "$SRC/frontend/out/" "$P/web/"
chown -R "$RUN_USER:$RUN_USER" "$P/backend" "$P/database"
chown -R root:caddy "$P/web" 2>/dev/null || true
chmod -R a+rX "$P/web"

step "Entorno de Python"
[[ -d "$P/venv" ]] || sudo -u "$RUN_USER" python3 -m venv "$P/venv"
sudo -u "$RUN_USER" "$P/venv/bin/pip" install -q --upgrade pip
sudo -u "$RUN_USER" "$P/venv/bin/pip" install -q -r "$P/backend/requirements.txt"

# ---------------------------------------------------------------- base de datos
step "PostgreSQL"
systemctl enable --now postgresql
if [[ ! -f "$P/portal.env" ]]; then
  DBPASS=$(openssl rand -hex 16)
  SECRET=$(openssl rand -hex 32)
  sudo -u postgres psql -qv ON_ERROR_STOP=1 <<SQL
DO \$\$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='portal') THEN
    CREATE ROLE portal LOGIN PASSWORD '$DBPASS';
  ELSE
    ALTER ROLE portal PASSWORD '$DBPASS';
  END IF;
END \$\$;
SQL
  sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='portal'" | grep -q 1 \
    || sudo -u postgres createdb -O portal portal
  sed -e "s#postgresql://portal:CAMBIAR@#postgresql://portal:$DBPASS@#" \
      -e "s#^APP_SECRET_KEY=.*#APP_SECRET_KEY=$SECRET#" \
      "$SRC/deploy/portal.env.example" > "$P/portal.env"
  echo "Creado $P/portal.env (agrega ZABBIX_API_TOKEN para ver el monitoreo en el portal)"
fi
chown "$RUN_USER:$RUN_USER" "$P/portal.env"
chmod 600 "$P/portal.env"
# Extensiones con superusuario (la migración 001 las usa)
sudo -u postgres psql -qd portal -c "CREATE EXTENSION IF NOT EXISTS pgcrypto; CREATE EXTENSION IF NOT EXISTS btree_gist;"

install -m 755 "$SRC/deploy/portalctl" /usr/local/bin/portalctl

step "Migraciones"
portalctl migrate

# ---------------------------------------------------------------- servicios
step "Servicios systemd"
for s in portal-api portal-worker; do
  sed -e "s#__USER__#$RUN_USER#g" -e "s#__HOME__#$RUN_HOME#g" \
      "$SRC/deploy/systemd/$s.service" > "/etc/systemd/system/$s.service"
done
systemctl daemon-reload
systemctl enable portal-api portal-worker
systemctl restart portal-api portal-worker

step "Caddy (HTTPS con certificado para la IP)"
install -d -o caddy -g caddy /var/log/caddy
sed -e "s#__PUBLIC_IP__#$PUBLIC_IP#g" "$SRC/deploy/Caddyfile.tpl" > /etc/caddy/Caddyfile
if [[ -n "${ACME_EMAIL:-}" ]]; then
  sed -i "s#__ACME_EMAIL__#$ACME_EMAIL#" /etc/caddy/Caddyfile
else
  sed -i "/__ACME_EMAIL__/d" /etc/caddy/Caddyfile
fi
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# validate corre como root y puede crear portal.log con dueño root: el servicio corre como caddy
chown -R caddy:caddy /var/log/caddy
systemctl enable caddy
systemctl reload caddy || systemctl restart caddy

step "Comprobación"
sleep 2
curl -fsS http://127.0.0.1:8000/api/v1/health && echo
systemctl --no-pager --lines=0 status portal-api portal-worker caddy | grep -E "●|Active:"
cat <<EOF

Listo. Portal: https://$PUBLIC_IP/portal_heladeria/

Si es la primera instalación:
  1) Security group de la EC2: abrir 80/tcp y 443/tcp (80 lo usa Let's Encrypt).
  2) Crear el administrador (pide la contraseña):
       sudo portalctl create-user --username admin --email admin@heladeria.local --name "Administrador" --role admin
  3) Importar los sitios que ya existen (ver docs/runbooks/portal.md).
EOF
