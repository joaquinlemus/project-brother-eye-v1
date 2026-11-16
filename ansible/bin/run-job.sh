#!/usr/bin/env bash
# Interfaz única entre el portal y Ansible.
#
#   run-job.sh <job_id> <provision|decommission|forget|verify> <hostname> [--check]
#
# Antes de llamarlo, el portal escribe inventories/site_<hostname>.yml con los datos del IPAM.
# Deja en /opt/xyz/jobs/<job_id>/: ansible.log, rc (código de salida), backups/.
# Variable opcional SKIP_TAGS (ej. SKIP_TAGS=zabbix mientras Zabbix no esté listo).
set -euo pipefail

JOB_ID="${1:?falta job_id}"
ACTION="${2:?falta acción}"
HOST="${3:?falta hostname}"
CHECK="${4:-}"

BASE="${XYZ_BASE:-/opt/xyz}"
ANS="$BASE/ansible"

case "$ACTION" in
  provision)    PLAYBOOK=site_provision.yml ;;
  decommission) PLAYBOOK=site_decommission.yml ;;
  verify)       PLAYBOOK=site_verify.yml ;;
  forget)       PLAYBOOK=site_forget.yml ;;   # router que ya no responde: no se conecta a él
  *) echo "Acción inválida: $ACTION" >&2; exit 2 ;;
esac

# Validación estricta: estos valores llegan desde el portal
[[ "$JOB_ID" =~ ^[A-Za-z0-9-]{1,64}$ ]] || { echo "job_id inválido" >&2; exit 2; }
[[ "$HOST" =~ ^R[0-9]{1,3}$ ]]          || { echo "hostname inválido: $HOST" >&2; exit 2; }
[[ -z "$CHECK" || "$CHECK" == "--check" ]] || { echo "4.º argumento solo puede ser --check" >&2; exit 2; }
[[ "$HOST" != "R1" && "$HOST" != "R2" ]] || { echo "Los hubs no se aprovisionan desde el portal" >&2; exit 2; }

SITE_INV="$ANS/inventories/site_${HOST}.yml"
[[ -f "$SITE_INV" ]] || { echo "No existe $SITE_INV" >&2; exit 2; }

OUT="$BASE/jobs/$JOB_ID"
mkdir -p "$OUT"

# shellcheck disable=SC1091
source "$BASE/venv/bin/activate"
cd "$ANS"

export ANSIBLE_VAULT_PASSWORD_FILE="${ANSIBLE_VAULT_PASSWORD_FILE:-$BASE/.vault_pass}"
export ANSIBLE_LOG_PATH="$OUT/ansible.log"
export PORTAL_JOB_ID="$JOB_ID"

ARGS=(-i inventories/lab.yml -i "$SITE_INV" "playbooks/$PLAYBOOK"
      --limit "$HOST,hubs" -e "artifacts_dir=$OUT")
[[ -n "${SKIP_TAGS:-}" ]] && ARGS+=(--skip-tags "$SKIP_TAGS")
[[ -n "$CHECK" ]] && ARGS+=(--check --diff)

set +e
ansible-playbook "${ARGS[@]}"
RC=$?
set -e
echo "$RC" > "$OUT/rc"
exit "$RC"
