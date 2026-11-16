#!/usr/bin/env bash
# run-job.sh simulado para pruebas: imita la salida de ansible-playbook.
# Falla si existe $XYZ_BASE/fail_<HOST>.
JOB_ID=$1; ACTION=$2; HOST=$3
OUT="$XYZ_BASE/jobs/$JOB_ID"; mkdir -p "$OUT"
[[ -f "$XYZ_BASE/ansible/inventories/site_${HOST}.yml" ]] || { echo "No existe site_${HOST}.yml" >&2; exit 2; }
task() { printf '\nTASK [%s] %s\n' "$1" '*********'; echo "$2: [$HOST]"; }
if [[ $ACTION == provision ]]; then
  task "Probar SSH en la IP underlay" "ok"
  for r in "fvrf : Verificar VRF" "base : Configuración base" "crypto_ikev2 : IKEv2" \
           "lan : LAN" "dmvpn_spoke : Túneles" "routing : OSPF" "snmpv3 : SNMPv3"; do
    task "$r" "changed"
  done
  if [[ -f "$XYZ_BASE/fail_$HOST" ]]; then
    task "verify : Esperar 2 vecinos OSPF FULL" "fatal"
    echo "fatal: [$HOST]: FAILED! => {\"msg\": \"Solo 1 vecino OSPF FULL\"}"
    printf '\nPLAY RECAP ***\n%s : ok=8 changed=7 unreachable=0 failed=1 skipped=0 rescued=0 ignored=0\n' "$HOST"
    exit 2
  fi
  task "verify : Esperar 2 vecinos OSPF FULL" "ok"
  task "zabbix_host : Crear host" "changed"
else
  task "zabbix_host : Deshabilitar host" "changed"
  task "decommission : Retirar configuración" "changed"
  task "Consultar NHRP y OSPF" "ok"
fi
printf '\nPLAY RECAP ***\n%s : ok=12 changed=9 unreachable=0 failed=0 skipped=1 rescued=0 ignored=0\n' "$HOST"
printf 'R1 : ok=2 changed=0 unreachable=0 failed=0 skipped=0 rescued=0 ignored=0\n'
exit 0
