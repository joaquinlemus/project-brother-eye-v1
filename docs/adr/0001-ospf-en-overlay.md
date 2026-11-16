# ADR 0001 — OSPF como protocolo del overlay

- **Estado:** aceptado (configuración probada en el laboratorio el 2026-11-06)
- **Fecha:** 2026-11-04, actualizado 2026-11-06

## Contexto

El enunciado dice que OSPF es el protocolo dinámico del diseño, pero el flujo de alta y las
pruebas de aceptación 3 y 9 mencionan sesiones BGP. Se necesita que agregar un sitio no requiera
tocar los hubs.

## Decisión

OSPFv2 + OSPFv3 (sintaxis `router ospfv3` / `ospfv3 1 ipv6 area 0`) en área 0, con red
`broadcast` en los túneles DMVPN:

- Cada hub es el DR de su nube (`priority 255`); los spokes tienen `priority 0`.
- Timers hello 5 s / dead 15 s.
- Costo 10 en `Tunnel0` (nube de R1) y 100 en `Tunnel1` (nube de R2): R1 es el hub preferido.
- Con red broadcast el siguiente salto hacia la LAN de otro spoke es ese spoke, así que el
  tráfico spoke a spoke abre un túnel directo resuelto por NHRP.

Las pruebas 3 y 9 se reinterpretan como "dos adyacencias OSPF FULL por spoke" y "sin vecino OSPF
ni entrada NHRP en los hubs".

## Consecuencias

- Todos los spokes comparten la LSDB del área 0: con decenas de sitios está bien; con cientos
  habría que pasar a BGP o a áreas por región.
- `roles/routing/templates/bgp.j2` mantiene una alternativa iBGP con `bgp listen range` en los
  hubs.
- Las plantillas se verifican contra la configuración real de R1, R2 y R3
  (`ansible/tests/compare_reference.py`).
