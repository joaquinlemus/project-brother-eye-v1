# Guion de la demostración en vivo (≈15 min)

## Antes de empezar
- [ ] WireGuard arriba: `wg show` en el Linux del lab (handshake < 2 min)
- [ ] Portal responde `/healthz`; sesión iniciada con MFA
- [ ] Zabbix muestra R1–R6 en verde
- [ ] Sitio de respaldo ya creado por si falla el alta en vivo
- [ ] Video de respaldo de la demo completa

## 1. Alta de un sitio (prueba 10)
1. Portal → Nueva sucursal → código y nombre → Reservar.
2. Mostrar recursos asignados por el IPAM (ID, LAN v4/v6, túneles).
3. Mostrar el job en vivo (pasos y eventos).
4. En R1 y R2: `show dmvpn` y `show ip ospf neighbor` → el nuevo spoke aparece.
5. En el spoke: `show crypto ikev2 sa` → 2 SA (prueba 1).
6. Zabbix: host nuevo en `Sucursales` con tag `sitio=<código>`.
7. Re-ejecutar el job → `changed=0` (prueba 8).

## 2. Spoke a spoke e IPv6 (pruebas 4, 6, 7)
1. Desde una VPC: `traceroute` a otra LAN dos veces → la segunda no pasa por el hub.
2. `ping <LAN remota> size 1400 df-bit` desde el router.
3. `ping` IPv6 entre LAN.

## 3. Falla de un hub (prueba 5)
1. Ping continuo entre dos LAN.
2. `shutdown` en `Ethernet0/0` de R1, cronometrar.
3. Converge por R2 en ≤ 45 s (dead OSPF = 20 s). Restaurar R1.

## 4. Baja del sitio (prueba 9)
1. Portal → Dar de baja → escribir el código.
2. Job: Zabbix deshabilitado → retiro de config → clear en hubs → Zabbix eliminado.
3. En hubs: sin NHRP ni vecino OSPF del sitio. En Zabbix: sin host. En IPAM: recursos en cuarentena.
4. Mostrar la auditoría completa del sitio.
