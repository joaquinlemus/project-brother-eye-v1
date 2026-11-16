// Misma regla que el backend (app/domain/ipam/addressing.py), solo para vistas previas.
export interface Rule { D: number; MMDD: string; max_site_id: number }

export function derive(s: number, r: Rule) {
  return [
    ["Underlay (gestión, VRF INET)", `172.16.0.${s}/24`],
    ["Loopback0", `10.254.0.${s}/32`],
    ["LAN IPv4", `10.${r.D + s}.0.0/24`],
    ["LAN IPv6", `2001:${r.MMDD}:${s}::/64`],
    ["Tunnel0 hacia Hub 1", `192.168.5.${s}/25 y FD00:5::${s}/64`],
    ["Tunnel1 hacia Hub 2", `192.168.5.${130 + s}/25 y FD00:5:1::${s}/64`],
  ] as const;
}
