# Portal de la Heladería Leche de Cabra en la EC2

El portal corre en la misma EC2 que Ansible y llama a `bin/run-job.sh`. Queda en
`https://<IP-pública>/portal_heladeria/`.

```
Internet ──HTTPS 443──> Caddy (certificado Let's Encrypt para la IP)
                          ├── /portal_heladeria/api/*  -> FastAPI 127.0.0.1:8000   (portal-api)
                          └── /portal_heladeria/*      -> archivos estáticos        (/opt/xyz/portal/web)
FastAPI ──> PostgreSQL local (portal)            usuarios, sitios, IPAM, jobs, auditoría
Worker  ──> cola en PostgreSQL ──> run-job.sh ──> Ansible ──WireGuard──> routers y Zabbix
API     ──> Zabbix (solo lectura) para mostrar el estado SNMP
```

| Pieza | Dónde |
|---|---|
| Código del portal | `/opt/xyz/portal/backend`, `/opt/xyz/portal/web` |
| Configuración y secretos | `/opt/xyz/portal/portal.env` (chmod 600) |
| Logs de cada job | `/opt/xyz/jobs/<job_id>/console.log` y `ansible.log` |
| Servicios | `portal-api`, `portal-worker`, `caddy`, `postgresql` |
| Administración | `sudo portalctl ...` |

## 1. Antes de instalar (consola de AWS)

1. **IP elástica.** Asóciala a la EC2. El certificado se emite para esa IP; si la IP cambia al
   reiniciar la instancia, el portal deja de ser válido.
2. **Security group.** Entrada `443/tcp` y `80/tcp` desde `0.0.0.0/0`. El 80 lo usa Let's Encrypt
   para validar la IP y luego redirige a HTTPS. Deja SSH (22) solo desde tu IP o la VPN.

## 2. Instalar

Desde tu PC:

```bash
scp xyz-sdn-portal.zip user2@<IP-WireGuard-EC2>:/tmp/
```

En la EC2:

```bash
cd /tmp && rm -rf xyz-sdn-portal && unzip -q xyz-sdn-portal.zip && cd xyz-sdn-portal
sudo PUBLIC_IP=<ip-elastica> ACME_EMAIL=<tu-correo> bash deploy/install.sh
```

El script instala PostgreSQL, Caddy y el entorno de Python, crea la base y `portal.env` con
claves aleatorias, aplica las migraciones y levanta los servicios. No toca la carpeta
`/opt/xyz/ansible` ni el vault. Para actualizar, se corre el mismo comando con el zip nuevo.

## 3. Primer uso

```bash
# Administrador (pide la contraseña: mínimo 10 caracteres, letras y números)
sudo portalctl create-user --username admin --email admin@heladeria.local --name "Jorge Soto" --role admin

# Sitios que ya existen. R3 y R4 se configuraron a mano: protegidos (no se pueden dar de baja)
sudo portalctl import-site --site-id 3 --code MAZ-03 --name "Mazate" --protected
sudo portalctl import-site --site-id 4 --code SPOKE-R4 --name "SPOKE-R4" --protected
# R6 se dio de alta con Ansible por CLI: importarlo sin protección (se puede dar de baja)
sudo portalctl import-site --site-id 6 --code SPOKE-R6 --name "SPOKE-R6"
```

R5 no se importa: quedó dado de baja, así que el portal lo ofrece como primer router libre.

Monitoreo en el portal (opcional, solo lectura): pega el mismo token de API de Zabbix.

```bash
sudo nano /opt/xyz/portal/portal.env      # ZABBIX_API_TOKEN=<token>
sudo systemctl restart portal-api portal-worker
```

Abre `https://<ip-elastica>/portal_heladeria/`, entra con `admin` y escanea el QR con Google
Authenticator o Microsoft Authenticator. A partir de ahí cada ingreso pide el código de 6 dígitos.

## 4. Demostración: alta y baja de R5

1. **Sucursales > Dar de alta una sucursal.** Nombre "Heladería Zona 10", código `Z10`, router R5.
   El panel derecho muestra el direccionamiento que se reservará.
2. El portal abre el trabajo: los 11 pasos se marcan mientras Ansible avanza y la salida aparece
   en vivo. Al terminar, la sucursal queda **Activa** y R5 aparece en Zabbix.
3. **Inicio** muestra R5 en la topología con sus dos túneles.
4. En la sucursal, **Dar de baja**: hay que escribir `Z10` y un motivo. Ansible retira la
   configuración, Zabbix elimina el host y las direcciones quedan **en cuarentena** (1 día).
5. Para volver a usar R5 de inmediato: en la sucursal retirada, **Liberar cuarentena**
   (solo administrador; queda en la auditoría).
6. **Auditoría > Verificar integridad** demuestra que nadie alteró el registro.

## 5. Roles

| Rol | Puede |
|---|---|
| Administrador | Todo, incluidos usuarios, liberar cuarentenas y retirar sucursales que no responden |
| Operador de red | Altas, bajas, reintentos, ver IPAM, comparar con Zabbix |
| Auditor | Ver inventario, trabajos, IPAM y auditoría |
| Lector | Ver inventario, trabajos e IPAM |

## 6. Operación

```bash
journalctl -u portal-worker -f          # qué está ejecutando el worker
journalctl -u portal-api -n 50          # errores de la API
sudo tail -f /var/log/caddy/portal.log  # accesos
sudo portalctl reset-mfa --username admin   # si alguien pierde el celular
sudo -u postgres pg_dump portal > /tmp/portal-$(date +%F).sql   # respaldo
```

Si un job queda interrumpido (reinicio de la EC2 o del servicio), el worker lo marca como
fallido al arrancar y se puede **Reintentar** desde el portal.

### Sucursales sin conectividad

- Cada minuto el worker prueba cada sucursal activa (TCP 22 y, si no hay respuesta, ping) en
  su IP de underlay `172.16.0.s`. Con 2 pruebas fallidas seguidas la sucursal pasa a
  **No disponible**: círculo rojo en el mapa y estado rojo en la lista.
- Si tampoco responden R1 y R2, el problema es el enlace al laboratorio (WireGuard o el nodo
  Linux): no se marca ninguna sucursal.
- A los 30 minutos sin respuesta, el portal pregunta a los administradores si la sucursal se
  eliminó. **No, sigue en servicio** vuelve a preguntar 30 minutos después.
  **Sí, retirar monitoreo** crea un trabajo *Retiro sin conexión* (`run-job.sh … forget`): quita
  el host de Zabbix y limpia NHRP en los hubs, sin conectarse al router. La sucursal pasa a
  Retirada y sus direcciones a cuarentena.
- El router retirado así conserva su configuración. Si vuelve a aparecer, bórrala antes de
  reutilizarlo, porque intentaría registrarse otra vez en los hubs.
- Las sucursales protegidas (R3, R4) se marcan en rojo, pero no se pregunta por ellas.

## Actualizar

Con un zip nuevo, el mismo comando de instalación actualiza el código, aplica migraciones y
reinicia los servicios. Conserva `portal.env`, la base de datos, los usuarios y el certificado.

```bash
cd /tmp && rm -rf xyz-sdn-portal && unzip -q xyz-sdn-portal.zip && cd xyz-sdn-portal
sudo PUBLIC_IP=184.195.236.235 bash deploy/install.sh
```

El instalador no toca `/opt/xyz/ansible`. Si el zip trae playbooks nuevos, cópialos a mano
(ejemplo: el retiro sin conexión):

```bash
cp ansible/playbooks/site_forget.yml /opt/xyz/ansible/playbooks/
cp ansible/bin/run-job.sh /opt/xyz/ansible/bin/run-job.sh
```

## 7. Problemas comunes

| Síntoma | Causa y solución |
|---|---|
| El navegador dice que el certificado no es válido | Caddy no obtuvo el certificado: `journalctl -u caddy -n 50`. Revisa que el puerto 80 esté abierto y que `PUBLIC_IP` sea la IP elástica. Plan B: en `/etc/caddy/Caddyfile` cambia el bloque `tls { issuer acme ... }` por `tls internal` y `systemctl reload caddy` (certificado propio: el navegador pedirá aceptar la excepción). |
| 502 Bad Gateway | `portal-api` no corre: `systemctl status portal-api` y `journalctl -u portal-api -n 50`. |
| Inicio dice "Motor de Ansible sin señal" | `systemctl restart portal-worker`. |
| El job falla en "Conectividad SSH" | El router no tiene day-0 o WireGuard está caído (`wg show`). |
| El job falla en "Monitoreo en Zabbix" | Token vacío en el vault de Ansible o Zabbix caído. El router ya quedó configurado: corrige y usa Reintentar. |
| "R5 no está disponible: QUARANTINED" | Libera la cuarentena desde la sucursal retirada (administrador). |
| "R20 está reservado" o "R71 está reservado" | Correcto: R20 tendría el underlay 172.16.0.20 (Ubuntu de Zabbix) y R71 la LAN 10.99.0.0/24 (WireGuard). Se calculan con `RESERVED_UNDERLAY_HOSTS` y `RESERVED_NETWORKS` de `portal.env`. El portal no muestra el motivo para no exponer la infraestructura; queda en `journalctl -u portal-api`. |
| Cuenta bloqueada | 5 intentos fallidos bloquean 15 minutos. El administrador puede asignar una contraseña temporal en Usuarios, lo que también desbloquea. |
