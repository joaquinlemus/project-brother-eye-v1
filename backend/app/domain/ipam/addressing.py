"""AddressingPlan: deriva todo el direccionamiento de un sitio a partir de su ID s.

Reglas del enunciado:
  LAN IPv4  10.(D+s).0.0/24         (segunda LAN mediana: 10.(D+s).1.0/24)
  LAN IPv6  2001:MMDD:s::/64        (segunda: 2001:MMDD:s:1::/64), sin ceros a la izquierda
  Loopback  10.254.0.s/32
  Underlay  172.16.0.s/24
Segmentos de túnel del equipo: 192.168.5.0/24 dividido en dos /25, uno por nube DMVPN:
  Tunnel1   192.168.5.s/25         (nube Hub 1, 192.168.5.0/25;   Hub 1 = .1)
  Tunnel2   192.168.5.(130+s)/25   (nube Hub 2, 192.168.5.128/25; Hub 2 = .132)
IPv6 de túnel (configuración probada en el laboratorio; s con sus dígitos decimales):
  Tunnel0   FD00:5::s/64     (nube Hub 1; R1 = ::1)
  Tunnel1   FD00:5:1::s/64   (nube Hub 2; R2 = ::2)
  Link-local FE80::s en ambos túneles
"""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass

from app.domain.errors import DomainError

FIRST_SPOKE_ID = 3          # 1 y 2 son los hubs
TUNNEL_NET = "192.168.5"    # ambos /25 viven en este /24
TUNNEL2_OFFSET = 130        # Tunnel2 = 192.168.5.(130+s)
MAX_TUNNEL_ID = 254 - TUNNEL2_OFFSET   # 130+s <= 254 (.255 es broadcast) -> s <= 124


@dataclass(frozen=True)
class TeamBirthday:
    month: int   # MM
    day: int     # D

    def __post_init__(self) -> None:
        if not (1 <= self.month <= 12 and 1 <= self.day <= 31):
            raise DomainError("Fecha de cumpleaños inválida")

    @property
    def mmdd(self) -> str:
        # "sin ceros a la izquierda": 12/28 -> 1228 ; 03/05 -> 305
        return f"{self.month}{self.day:02d}"

    @property
    def max_site_id(self) -> int:
        # Dos límites; manda el menor:
        #  - LAN 10.(D+s) no puede llegar a 10.254 (loopbacks)       -> s <= 253 - D (D=28: 225)
        #  - Tunnel1 192.168.5.s/25                                   -> s <= 126
        #  - Tunnel2 192.168.5.(130+s)/25                             -> s <= 124  (manda este)
        return min(253 - self.day, MAX_TUNNEL_ID)


@dataclass(frozen=True)
class SiteAddressing:
    site_id: int
    underlay: ipaddress.IPv4Interface
    loopback0: ipaddress.IPv4Network
    lan_v4: list[ipaddress.IPv4Network]
    lan_v6: list[ipaddress.IPv6Network]
    tunnel1_v4: ipaddress.IPv4Interface
    tunnel2_v4: ipaddress.IPv4Interface
    tunnel1_v6: ipaddress.IPv6Interface
    tunnel2_v6: ipaddress.IPv6Interface


class AddressingPlan:
    def __init__(self, birthday: TeamBirthday) -> None:
        self.bd = birthday

    def validate_site_id(self, s: int) -> None:
        if not (FIRST_SPOKE_ID <= s <= self.bd.max_site_id):
            raise DomainError(
                f"Site ID {s} fuera de rango [{FIRST_SPOKE_ID}, {self.bd.max_site_id}]"
            )

    def derive(self, s: int, medium: bool = False) -> SiteAddressing:
        self.validate_site_id(s)
        second = self.bd.day + s
        mmdd = self.bd.mmdd
        lan_v4 = [ipaddress.IPv4Network(f"10.{second}.0.0/24")]
        lan_v6 = [ipaddress.IPv6Network(f"2001:{mmdd}:{s}::/64")]
        if medium:
            lan_v4.append(ipaddress.IPv4Network(f"10.{second}.1.0/24"))
            lan_v6.append(ipaddress.IPv6Network(f"2001:{mmdd}:{s}:1::/64"))
        return SiteAddressing(
            site_id=s,
            underlay=ipaddress.IPv4Interface(f"172.16.0.{s}/24"),
            loopback0=ipaddress.IPv4Network(f"10.254.0.{s}/32"),
            lan_v4=lan_v4,
            lan_v6=lan_v6,
            tunnel1_v4=ipaddress.IPv4Interface(f"{TUNNEL_NET}.{s}/25"),
            tunnel2_v4=ipaddress.IPv4Interface(f"{TUNNEL_NET}.{TUNNEL2_OFFSET + s}/25"),
            tunnel1_v6=ipaddress.IPv6Interface(f"fd00:5::{s}/64"),
            tunnel2_v6=ipaddress.IPv6Interface(f"fd00:5:1::{s}/64"),
        )


def reserved_site_ids(plan: AddressingPlan, candidates: range, underlay_hosts: list[str],
                      networks: list[str]) -> dict[int, str]:
    """Site IDs inutilizables porque su direccionamiento pisa infraestructura del laboratorio.

    Se calculan (no se fijan a mano): un ID queda reservado si su underlay es la IP de un servidor
    (p. ej. 172.16.0.20, el Ubuntu de Zabbix) o si alguna de sus LAN se solapa con una red
    reservada (p. ej. 10.99.0.0/24, WireGuard: con D=28 la tendría el sitio 71).
    Devuelve {id: motivo}.
    """
    hosts = {ipaddress.ip_address(h) for h in underlay_hosts}
    nets = [ipaddress.ip_network(n) for n in networks]
    out: dict[int, str] = {}
    for s in candidates:
        a = plan.derive(s, medium=True)       # se revisan también las LAN de un sitio mediano
        if a.underlay.ip in hosts:
            out[s] = f"su underlay {a.underlay.ip} es un servidor del laboratorio"
            continue
        for lan in [*a.lan_v4, *a.lan_v6]:
            hit = next((n for n in nets if n.version == lan.version and lan.overlaps(n)), None)
            if hit:
                out[s] = f"su LAN {lan} se solapa con la red reservada {hit}"
                break
    return out


def first_free(candidates: range, used: set[int]) -> int | None:
    """First-fit: el menor ID libre (no asignado ni en cuarentena)."""
    return next((s for s in candidates if s not in used), None)
