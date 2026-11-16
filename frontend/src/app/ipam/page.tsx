"use client";
import Box from "@mui/material/Box";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import { Empty, LoadError, Loading, Mono, PageHeader, Section } from "@/components/Page";
import { AllocStatusChip } from "@/components/Status";
import { ALLOC_STATUS, fmtDate, RESOURCE } from "@/lib/format";
import { C } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

interface Pool {
  id: number; name: string; resource: string; cidr: string | null; int_min: number | null; int_max: number | null;
  prefix_length: number | null; quarantine_days: number;
  reserved: number; allocated: number; quarantined: number; released: number;
}
interface Pools { rule: Record<string, string | number>; pools: Pool[] }
interface Alloc {
  id: number; pool: string; resource: string; prefix: string | null; int_value: number | null; status: string;
  reserved_at: string; quarantine_until: string | null; released_at: string | null;
  site_id: string; site_code: string; site_name: string;
}

function capacity(p: Pool): number | null {
  if (p.resource === "SITE_ID" && p.int_min !== null && p.int_max !== null) return p.int_max - p.int_min + 1;
  return null;
}

function Usage({ p }: { p: Pool }) {
  const total = capacity(p) ?? 124 - 2;
  const parts = [[p.allocated, C.pistacho], [p.reserved, C.barquillo], [p.quarantined, C.mora]] as const;
  return (
    <Box aria-label={`${p.allocated} asignados, ${p.reserved} reservados, ${p.quarantined} en cuarentena`}
      sx={{ display: "flex", height: 8, width: 140, borderRadius: 4, background: C.wash, overflow: "hidden" }}>
      {parts.map(([n, c], i) => n > 0 && (
        <Box key={i} sx={{ width: `${Math.max(3, (n / total) * 100)}%`, background: c }} />
      ))}
    </Box>
  );
}

function Ipam() {
  const pools = useApi<Pools>("/ipam/pools", 10000);
  const [st, setSt] = useState("");
  const allocs = useApi<Alloc[]>(`/ipam/allocations?limit=300${st ? `&status=${st}` : ""}`, 10000);
  if (pools.error) return <LoadError error={pools.error} retry={pools.reload} />;
  if (!pools.data) return <Loading />;
  const r = pools.data.rule;
  return (
    <>
      <PageHeader title="IPAM"
        subtitle="Todo el direccionamiento sale del Site ID s. La base de datos impide que dos sucursales vivas compartan un ID o un prefijo." />
      <Section title="Regla de asignación">
        <Box sx={{ display: "grid", gridTemplateColumns: { sm: "repeat(3, 1fr)" }, gap: 2 }}>
          {[["Site ID", `primer libre entre 3 y ${r.max_site_id}`], ["LAN IPv4", r.lan_v4], ["LAN IPv6", r.lan_v6],
            ["Loopback0", r.loopback], ["Tunnel0 (Hub 1)", r.tunnel0], ["Tunnel1 (Hub 2)", r.tunnel1]].map(([k, v]) => (
            <Box key={k as string}>
              <Typography variant="body2" color="text.secondary">{k}</Typography>
              <Mono>{v}</Mono>
            </Box>
          ))}
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          D = {r.D}, MM = {r.MM}, MMDD = {r.MMDD}. Al dar de baja, los recursos pasan a cuarentena y no se reutilizan
          hasta que vence o un administrador la libera.
        </Typography>
      </Section>
      <Section title="Pools" pad={false}>
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Pool</TableCell><TableCell>Rango</TableCell><TableCell>Tamaño</TableCell>
              <TableCell>Uso</TableCell><TableCell align="right">Asignados</TableCell>
              <TableCell align="right">Reservados</TableCell><TableCell align="right">Cuarentena</TableCell>
              <TableCell align="right">Liberados</TableCell><TableCell>Cuarentena dura</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {pools.data.pools.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{RESOURCE[p.resource] ?? p.name}</TableCell>
                  <TableCell><Mono>{p.cidr ?? `${p.int_min}–${p.int_max}`}</Mono></TableCell>
                  <TableCell><Mono>{p.prefix_length ? `/${p.prefix_length}` : "entero"}</Mono></TableCell>
                  <TableCell><Usage p={p} /></TableCell>
                  <TableCell align="right">{p.allocated}</TableCell>
                  <TableCell align="right">{p.reserved}</TableCell>
                  <TableCell align="right">{p.quarantined}</TableCell>
                  <TableCell align="right">{p.released}</TableCell>
                  <TableCell>{p.quarantine_days ? `${p.quarantine_days} día${p.quarantine_days > 1 ? "s" : ""}` : "sin cuarentena"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Section>
      <Section title="Asignaciones" pad={false}
        aside={<TextField select label="Estado" value={st} onChange={(e) => setSt(e.target.value)} slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }} sx={{ width: 190 }}>
          <MenuItem value="">Todos</MenuItem>
          {Object.entries(ALLOC_STATUS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>}>
        {allocs.error ? <LoadError error={allocs.error} /> : !allocs.data ? <Loading /> : !allocs.data.length ?
          <Empty title="Sin asignaciones con este estado" /> : (
          <Box sx={{ overflowX: "auto", maxHeight: 560 }}>
            <Table size="small" stickyHeader>
              <TableHead><TableRow>
                <TableCell>Sucursal</TableCell><TableCell>Recurso</TableCell><TableCell>Valor</TableCell>
                <TableCell>Estado</TableCell><TableCell>Reservado</TableCell><TableCell>Cuarentena hasta</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {allocs.data.map((a) => (
                  <TableRow key={a.id} hover>
                    <TableCell>
                      <Box component={Link} href={`/sites/detail/?id=${a.site_id}`} sx={{ color: C.mora, textDecoration: "none" }}>
                        {a.site_name}
                      </Box>
                    </TableCell>
                    <TableCell>{RESOURCE[a.resource] ?? a.resource}</TableCell>
                    <TableCell><Mono>{a.prefix ?? a.int_value}</Mono></TableCell>
                    <TableCell><AllocStatusChip status={a.status} /></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtDate(a.reserved_at)}</TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{a.status === "QUARANTINED" ? fmtDate(a.quarantine_until) : "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Section>
    </>
  );
}

export default function Page() {
  return <AppShell><Ipam /></AppShell>;
}
