"use client";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import { BASE_PATH, type Site, type ZabbixHost } from "@/lib/api";
import { SITE_STATUS } from "@/lib/format";
import { C } from "@/lib/theme";
import { isUnreachable } from "@/lib/api";
import { siteMapColor } from "./Status";

const W = 960;

/** Mapa vivo de la red: dos hubs arriba, cada sucursal abajo con sus dos túneles. */
export default function Topology({ sites, hosts }: { sites: Site[]; hosts: ZabbixHost[] }) {
  const spokes = sites.filter((s) => s.status !== "RETIRED").sort((a, b) => a.site_number - b.site_number);
  const perRow = Math.min(Math.max(spokes.length, 1), 9);
  const rows = Math.max(1, Math.ceil(spokes.length / perRow));
  const H = 230 + rows * 120;
  const hubs = [
    { name: "R1", label: "Hub 1, primario", x: W * 0.32 },
    { name: "R2", label: "Hub 2, respaldo", x: W * 0.68 },
  ];
  const snmp = (h: string) => hosts.find((z) => z.host === h)?.snmp;
  const pos = (i: number) => {
    const row = Math.floor(i / perRow);
    const inRow = Math.min(perRow, spokes.length - row * perRow);
    const gap = W / (inRow + 1);
    return { x: gap * ((i % perRow) + 1), y: 250 + row * 120 };
  };

  return (
    <Box>
      <Box sx={{ overflowX: "auto" }}>
      <Box component="svg" viewBox={`0 0 ${W} ${H}`} role="img"
        aria-label={`Topología DMVPN: 2 hubs y ${spokes.length} sucursales`}
        sx={{ width: "100%", minWidth: 680, height: "auto", display: "block" }}>
        {spokes.map((s, i) => {
          const p = pos(i);
          const up = s.status === "ACTIVE" && !isUnreachable(s);
          return hubs.map((h, k) => (
            <line key={`${s.id}-${h.name}`} x1={p.x} y1={p.y - 26} x2={h.x} y2={96}
              stroke={up ? (k === 0 ? C.inkSoft : C.vainilla) : C.line}
              strokeWidth={k === 0 ? 1.6 : 1.2} strokeDasharray={k === 0 ? undefined : "5 5"} />
          ));
        })}
        {hubs.map((h) => (
          <g key={h.name}>
            <rect x={h.x - 62} y={36} width={124} height={60} rx={10} fill={C.ink} />
            <text x={h.x} y={63} textAnchor="middle" fill="#fff" fontSize={20} fontWeight={700}
              fontFamily="Bricolage Grotesque Variable">{h.name}</text>
            <text x={h.x} y={83} textAnchor="middle" fill="#B8C4D0" fontSize={12}>{h.label}</text>
            {snmp(h.name) && (
              <circle cx={h.x + 52} cy={46} r={5} fill={snmp(h.name) === "AVAILABLE" ? C.pistacho : C.fresa}
                stroke="#fff" strokeWidth={2} />
            )}
          </g>
        ))}
        {spokes.map((s, i) => {
          const p = pos(i);
          const z = snmp(s.hostname);
          const down = isUnreachable(s);
          return (
            <a key={s.id} href={`${BASE_PATH}/sites/detail/?id=${s.id}`}>
              <title>{`${s.hostname} ${s.name}: ${down ? "No disponible (sin conectividad)" : SITE_STATUS[s.status]}`}</title>
              {down && (
                <circle cx={p.x} cy={p.y} r={26} fill="none" stroke={C.fresa} strokeWidth={3}>
                  <animate attributeName="r" values="26;36;26" dur="1.6s" repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.7;0;0.7" dur="1.6s" repeatCount="indefinite" />
                </circle>
              )}
              <circle cx={p.x} cy={p.y} r={26} fill={siteMapColor(s)} />
              <text x={p.x} y={p.y + 5} textAnchor="middle" fill="#fff" fontSize={15} fontWeight={700}>
                {s.hostname}
              </text>
              <text x={p.x} y={p.y + 46} textAnchor="middle" fill={C.ink} fontSize={13}>
                {s.name.length > 16 ? `${s.name.slice(0, 15)}…` : s.name}
              </text>
              {z && (
                <circle cx={p.x + 20} cy={p.y - 20} r={5} fill={z === "AVAILABLE" ? C.pistacho : C.fresa}
                  stroke="#fff" strokeWidth={2} />
              )}
            </a>
          );
        })}
        {spokes.length === 0 && (
          <text x={W / 2} y={250} textAnchor="middle" fill={C.inkSoft} fontSize={15}>
            Aún no hay sucursales. Da de alta la primera desde Sucursales.
          </text>
        )}
      </Box>
      </Box>
      <Box sx={{ display: "flex", flexWrap: "wrap", gap: { xs: 1.5, sm: 3 }, px: 2.5, pb: 2, color: "text.secondary",
        fontSize: 13 }}>
        <Legend line="solid">Tunnel0 hacia Hub 1 (ruta preferida)</Legend>
        <Legend line="dashed">Tunnel1 hacia Hub 2 (respaldo)</Legend>
        <Legend dot={C.fresa} big>Sucursal sin conectividad</Legend>
        <Legend dot={C.pistacho}>SNMP responde en Zabbix</Legend>
        <Legend dot={C.fresa}>SNMP sin respuesta</Legend>
      </Box>
    </Box>
  );
}

function Legend({ children, line, dot, big }:
  { children: React.ReactNode; line?: "solid" | "dashed"; dot?: string; big?: boolean }) {
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 1 }}>
      {line && (
        <svg width="26" height="8" aria-hidden>
          <line x1="0" y1="4" x2="26" y2="4" stroke={line === "solid" ? C.inkSoft : C.vainilla} strokeWidth="1.6"
            strokeDasharray={line === "dashed" ? "5 4" : undefined} />
        </svg>
      )}
      {dot && <Box component="span" sx={{ width: big ? 16 : 10, height: big ? 16 : 10, borderRadius: "50%",
        background: dot }} />}
      <Typography component="span" sx={{ fontSize: 13 }}>{children}</Typography>
    </Box>
  );
}
