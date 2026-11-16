# ADR 0003 — Monitoreo SNMPv3 a través de la front-door VRF

- **Estado:** aceptado, sujeto a validación en el laboratorio
- **Fecha:** 2026-11-04

## Contexto

`Ethernet0/0` está en la VRF `INET`. Zabbix vive en el underlay (nube Net) y no alcanza la
Loopback0 del overlay. Los traps salen por defecto por la tabla global.

## Decisión

Zabbix consulta la IP underlay del router. En el router: grupo SNMPv3 con ACL que solo permite a
Zabbix, `snmp-server host <zabbix> vrf INET ...`, `snmp-server trap-source Ethernet0/0`, y syslog y
NTP con `vrf INET`.

## Validación requerida

`snmpwalk -v3 -l authPriv` desde Zabbix hacia `172.16.0.s` y `debug snmp packets` en el router.
Si la imagen IOS no responde consultas recibidas en la VRF, aplicar el plan B: ruta en Zabbix
hacia `10.254.0.0/24` vía un hub y leaking del /32 de Zabbix entre `INET` y la tabla global en los
hubs, documentado como excepción.
