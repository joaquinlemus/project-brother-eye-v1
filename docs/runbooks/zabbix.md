# Zabbix 7.0 LTS en el Ubuntu del lab + integración con Ansible

Servidor: Ubuntu 24.04 en 172.16.0.20 (el mismo del NTP y punto de salto).
Zabbix consulta a los routers por SNMPv3 en el underlay (VRF INET); la EC2 da de alta y de baja
los hosts llamando a la API por WireGuard.

```
EC2 (Ansible) --WireGuard--> 172.16.0.20/zabbix/api_jsonrpc.php   (alta/baja de hosts)
Zabbix 172.16.0.20 --SNMPv3 udp/161--> 172.16.0.x (Ethernet0/0, vrf INET)
```

## 1. Instalar (en 172.16.0.20, como root)

```bash
sudo -i
wget https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/zabbix-release_latest_7.0+ubuntu24.04_all.deb
dpkg -i zabbix-release_latest_7.0+ubuntu24.04_all.deb
apt update
apt install -y mysql-server
apt install -y zabbix-server-mysql zabbix-frontend-php zabbix-apache-conf zabbix-sql-scripts zabbix-agent
```

Si el `wget` da 404, abre https://repo.zabbix.com/zabbix/7.0/ubuntu/pool/main/z/zabbix-release/
y descarga el archivo que termina en `ubuntu24.04_all.deb`.

## 2. Base de datos

Cambia `ZbxDb2026` por la clave que quieras (y úsala igual en los 3 lugares).

```bash
mysql -uroot <<'SQL'
CREATE DATABASE zabbix CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
CREATE USER 'zabbix'@'localhost' IDENTIFIED BY 'ZbxDb2026';
GRANT ALL PRIVILEGES ON zabbix.* TO 'zabbix'@'localhost';
SET GLOBAL log_bin_trust_function_creators = 1;
SQL

# Tarda 1-3 minutos y no muestra nada mientras corre
zcat /usr/share/zabbix-sql-scripts/mysql/server.sql.gz | mysql --default-character-set=utf8mb4 -uzabbix -pZbxDb2026 zabbix

mysql -uroot -e "SET GLOBAL log_bin_trust_function_creators = 0;"
```

## 3. Configurar y arrancar

```bash
sed -i 's/^# DBPassword=.*/DBPassword=ZbxDb2026/' /etc/zabbix/zabbix_server.conf
grep ^DBPassword /etc/zabbix/zabbix_server.conf        # debe mostrar la clave

systemctl restart zabbix-server zabbix-agent apache2
systemctl enable  zabbix-server zabbix-agent apache2
systemctl status zabbix-server --no-pager | head -5    # active (running)
tail -20 /var/log/zabbix/zabbix_server.log             # sin "cannot connect to database"

ufw status        # si está "active": ufw allow 80/tcp
```

## 4. Asistente web

Abre `http://172.16.0.20/zabbix`. Si tu PC no enruta 172.16.0.0/24 por WireGuard, usa un túnel
por la EC2: `ssh -L 8080:172.16.0.20:80 user2@<IP-WireGuard-EC2>` y abre `http://localhost:8080/zabbix`.

1. Idioma: el que quieras → Next.
2. Requisitos: todo OK → Next.
3. Base de datos: MySQL, host `localhost`, base `zabbix`, usuario `zabbix`, clave `ZbxDb2026`.
4. Servidor: nombre `Heladeria-NOC`, zona horaria `America/Guatemala`.
5. Finish. Entra con `Admin` / `zabbix` y **cambia la clave** (Usuario > Perfil).

## 5. Token de API para Ansible

Usuarios > Tokens de API > Crear token de API:
- Nombre: `ansible-ec2`
- Usuario: `Admin`
- Fecha de expiración: desmarcada (laboratorio)

Copia el token: solo se muestra una vez. En la EC2:

```bash
cd /opt/xyz/ansible
export ANSIBLE_VAULT_PASSWORD_FILE=/opt/xyz/.vault_pass
ansible-vault edit inventories/group_vars/all/vault.yml
#   zabbix_api_token: "<token>"
```

En producción el token sería de un usuario de servicio con rol Admin y permiso de escritura solo
sobre los grupos Hubs y Sucursales, no del Super Admin.

## 6. Probar desde la EC2

```bash
source /opt/xyz/venv/bin/activate && cd /opt/xyz/ansible
export ANSIBLE_VAULT_PASSWORD_FILE=/opt/xyz/.vault_pass

# Alcance de red (sin token)
curl -s -X POST -H 'Content-Type: application/json-rpc' \
  -d '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' \
  http://172.16.0.20/zabbix/api_jsonrpc.php

# Token, grupos y plantilla
ansible-playbook playbooks/zabbix_check.yml
```

`zabbix_check.yml` debe mostrar la versión 7.0.x y la plantilla `Cisco IOS by SNMP`. Los grupos
`Hubs` y `Sucursales` pueden no existir todavía: el rol los crea.

## 7. Registrar los routers que ya existen (R1-R4)

No se conecta a los routers; solo llama a la API.

```bash
cp inventories/examples/site_R3.yml inventories/examples/site_R4.yml inventories/
ansible-playbook -i inventories/lab.yml -i inventories/site_R3.yml -i inventories/site_R4.yml \
    playbooks/zabbix_register.yml
```

Correrlo dos veces: la segunda debe dar `changed=0` en todos.

## 8. Aprovisionamiento y baja con monitoreo

Ya no hace falta `SKIP_TAGS=zabbix`:

```bash
bin/run-job.sh r5-alta provision R5        # al final: "Zabbix (present) - R5" → host creado
bin/run-job.sh r5-baja decommission R5     # primero deshabilita, al final elimina el host
```

Orden en el alta: el host se registra **después** de la verificación (IKEv2, NHRP y OSPF arriba),
así Zabbix nunca monitorea un sitio a medio configurar. En la baja se deshabilita antes de tocar el
router (sin tormenta de alertas) y se elimina al final.

## Qué crea el rol en Zabbix

| Campo | Valor |
|---|---|
| Host (nombre técnico) | `R5` (= hostname del router) |
| Nombre visible | `R5 - <site_name>`; hubs: `R1 - HUB-1` |
| Grupo | `Hubs` o `Sucursales` (se crea si no existe) |
| Plantilla | `Cisco IOS by SNMP` |
| Interfaz | SNMPv3 authPriv, SHA1/AES128, IP underlay 172.16.0.s, puerto 161 |
| Tags | `sitio`, `rol` (hub/spoke), `gestionado_por=portal-xyz` |

El rol es idempotente: compara nombre, estado, grupo, plantillas, tags, IP y usuario SNMP, y solo
actualiza si algo difiere. Un error de la API (token inválido, plantilla inexistente) detiene el
job con el mensaje de Zabbix; las fallas de red se reintentan 3 veces.

## Problemas comunes

| Síntoma | Causa probable |
|---|---|
| `Not authorized` | Token vacío, mal copiado o expirado |
| `Faltan plantillas en Zabbix` | Nombre distinto de `Cisco IOS by SNMP` en `group_vars/all/main.yml` |
| Ícono SNMP rojo, "Timeout" | ACL-SNMP del router no permite 172.16.0.20, o falta `vrf INET` en el host SNMP |
| Ícono SNMP rojo, "Unknown user name" / "Authentication failure" | Claves SNMP del vault ≠ las del router |
| Timeout desde la EC2 a la API | Túnel WireGuard caído (`wg show`, handshake reciente) |

Prueba manual desde el Ubuntu, con las mismas credenciales que usa Zabbix:

```bash
snmpget -v3 -l authPriv -u zbxuser -a SHA -A ZbxAuth2026 -x AES -X ZbxPriv2026 172.16.0.5 sysName.0
```
