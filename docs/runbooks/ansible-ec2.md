# Configurar Ansible en la EC2

Objetivo: dejar Ansible listo en la EC2 para que el portal lo llame con `bin/run-job.sh`.

## Estructura en el servidor

```
/opt/xyz/
├── venv/            # Python + Ansible
├── ansible/         # carpeta ansible/ del repositorio
├── .vault_pass      # clave de Ansible Vault (chmod 600, fuera del repo)
└── jobs/<job_id>/   # ansible.log, rc y respaldos de cada ejecución
```

## 1. Copiar la carpeta ansible/ al servidor

Desde tu equipo (conectado a la VPN WireGuard):

```bash
scp -r xyz-sdn-portal/ansible user2@<IP-WireGuard-de-la-EC2>:/opt/xyz/
```

## 2. Dependencias de Python y colecciones

```bash
pip install -r /opt/xyz/ansible/requirements-python.txt
```

`paramiko<4` es obligatorio: paramiko 4+ no tiene el intercambio de llaves SHA-1
que usa IOS 15.7.

### Colecciones

```bash
source /opt/xyz/venv/bin/activate
cd /opt/xyz/ansible
ansible-galaxy collection install -r requirements.yml
ansible --version          # debe leer /opt/xyz/ansible/ansible.cfg
```

## 3. Secretos con Ansible Vault

Siempre desde `/opt/xyz/ansible`. La ruta de la clave va en una variable de entorno
(`run-job.sh` la define solo; esto es para los comandos a mano):

```bash
openssl rand -base64 32 > /opt/xyz/.vault_pass && chmod 600 /opt/xyz/.vault_pass
echo 'export ANSIBLE_VAULT_PASSWORD_FILE=/opt/xyz/.vault_pass' >> ~/.bashrc && source ~/.bashrc
cp inventories/group_vars/all/vault.yml.example inventories/group_vars/all/vault.yml
nano inventories/group_vars/all/vault.yml        # completar PSK, SNMPv3, token Zabbix
ansible-vault encrypt inventories/group_vars/all/vault.yml
ansible-vault view inventories/group_vars/all/vault.yml   # comprobar
```

## 4. Prueba de conexión a los hubs (solo lectura)

```bash
ansible hubs -m cisco.ios.ios_command -a "commands='show dmvpn'"
```

## 5. Prueba en modo check contra R3 (no cambia nada)

```bash
cp inventories/examples/site_R3.yml inventories/
SKIP_TAGS=zabbix,verify bin/run-job.sh prueba-r3 provision R3 --check
less /opt/xyz/jobs/prueba-r3/ansible.log
```

Debe mostrar diferencias solo en lo que R3 todavía no tiene (AAA, syslog, NTP por VRF,
banner, SNMPv3). Túneles, IPsec y OSPF no deberían cambiar.

**Nunca correr `decommission` sobre R3 o R4**: les borraría la configuración.

## 6. Primer spoke real

1. Crear el router en EVE-NG y aplicarle el day-0 (`docs/runbooks/day0-router.md`).
2. Copiar `inventories/examples/site_R3.yml` como `inventories/site_R<s>.yml` y cambiar los
   valores según las reglas del IPAM (s, LAN, túneles).
3. Ejecutar:

```bash
bin/run-job.sh prueba-r<s> provision R<s>
```

Incluye el registro en Zabbix (ver `docs/runbooks/zabbix.md`). Usa `SKIP_TAGS=zabbix` solo si
Zabbix no está disponible.

## Contrato con el portal

El portal (worker) hará exactamente esto por cada job:

1. Escribir `inventories/site_<HOST>.yml` con los datos del IPAM.
2. Ejecutar `bin/run-job.sh <job_id> <provision|decommission|verify> <HOST>`.
3. Leer `/opt/xyz/jobs/<job_id>/rc` (0 = éxito) y `ansible.log`.
