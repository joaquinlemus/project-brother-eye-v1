# Day-0 de routers (SSH + FVRF INET)

Configuración mínima para que un router nuevo acepte SSH desde la plataforma
(EC2 → WireGuard → Ubuntu 172.16.0.20 → routers). Está basada en la configuración real de R1.
Todo lo demás (IPsec, túneles, OSPF, LAN, SNMPv3) lo aplica Ansible después, por SSH.

En el repositorio está como `ansible/roles/day0_bootstrap/templates/day0.j2`; el rol la envía por
la consola de EVE-NG. Esta es la versión para pegar a mano.

Reemplazar: `<HOSTNAME>` (ej. R7), `<IP_UNDERLAY>` (172.16.0.s) y `<CLAVE_ANSIBLE>` (la misma
del vault de Ansible).

```
enable
configure terminal
hostname <HOSTNAME>
no ip domain lookup
ip domain name lab.local
service timestamps debug datetime msec
service timestamps log datetime msec
service password-encryption
!
vrf definition INET
 address-family ipv4
 exit-address-family
!
interface Ethernet0/0
 description Underlay (FVRF INET)
 vrf forwarding INET
 ip address <IP_UNDERLAY> 255.255.255.0
 no shutdown
!
username ansible privilege 15 secret <CLAVE_ANSIBLE>
!
ip ssh version 2
ip access-list standard MGMT
 permit 172.16.0.20
 deny   any log
!
line vty 0 4
 access-class MGMT in vrf-also
 login local
 transport input ssh
 exec-timeout 15 0
!
ntp server vrf INET 172.16.0.20
!
crypto key generate rsa general-keys modulus 2048
end
write memory
```

## Notas

- `vrf forwarding` borra la IP de la interfaz; por eso `ip address` va después.
- `access-class ... vrf-also` es obligatorio: sin `vrf-also`, el router rechaza SSH que llega por
  una interfaz en VRF.
- Las llaves RSA no aparecen en `show run`; si faltan, SSH no levanta.
- NTP va con `vrf INET`: sin eso el router busca el servidor en la tabla global, que no tiene
  salida. El Ubuntu debe correr un servidor NTP (chrony).
- Prueba desde la EC2: `ssh ansible@<IP_UNDERLAY>` debe entrar directo a `<HOSTNAME>#`.
