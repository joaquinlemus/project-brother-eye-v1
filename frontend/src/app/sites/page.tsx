"use client";
import AddIcon from "@mui/icons-material/Add";
import LockOutlined from "@mui/icons-material/LockOutlined";
import RemoveCircleOutline from "@mui/icons-material/RemoveCircleOutline";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Tab from "@mui/material/Tab";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Tabs from "@mui/material/Tabs";
import Tooltip from "@mui/material/Tooltip";
import Link from "next/link";
import { useState } from "react";
import AppShell, { can, useMe } from "@/components/AppShell";
import DecommissionDialog, { decommissionable } from "@/components/DecommissionDialog";
import { Empty, LoadError, Loading, Mono, PageHeader, Section } from "@/components/Page";
import { JobStatusChip, SiteChip } from "@/components/Status";
import type { Rule } from "@/lib/addressing";
import { isUnreachable, type Site } from "@/lib/api";
import { fmtDate, JOB_TYPE } from "@/lib/format";
import { C } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

const FILTERS: { key: string; label: string; match: (s: Site) => boolean }[] = [
  { key: "live", label: "En operación", match: (s) => s.status !== "RETIRED" },
  { key: "busy", label: "En proceso", match: (s) => s.status === "PROVISIONING" || s.status === "DECOMMISSIONING" },
  { key: "error", label: "Con error", match: (s) => s.status.endsWith("_FAILED") || isUnreachable(s) },
  { key: "retired", label: "Retiradas", match: (s) => s.status === "RETIRED" },
  { key: "all", label: "Todas", match: () => true },
];

function Sites() {
  const me = useMe();
  const { data, error, reload } = useApi<Site[]>("/sites", 5000);
  const rule = useApi<{ rule: Rule }>("/ipam/pools").data?.rule;
  const [filter, setFilter] = useState("live");
  const [baja, setBaja] = useState(false);
  if (error) return <LoadError error={error} retry={reload} />;
  if (!data) return <Loading />;
  const f = FILTERS.find((x) => x.key === filter)!;
  const rows = data.filter(f.match);
  return (
    <>
      <PageHeader title="Sucursales"
        subtitle="Cada sucursal es un router spoke R<s> con dos túneles DMVPN. El número s define todo su direccionamiento."
        actions={<>
          {can(me, "site:decommission") && (
            <Button variant="outlined" color="error" startIcon={<RemoveCircleOutline />}
              onClick={() => setBaja(true)}>
              Dar de baja una sucursal
            </Button>)}
          {can(me, "site:create") && (
            <Button component={Link} href="/sites/new/" variant="contained" startIcon={<AddIcon />}>
              Dar de alta una sucursal
            </Button>)}
        </>} />
      <Tabs value={filter} onChange={(_, v) => setFilter(v)} variant="scrollable" sx={{ mb: 1.5 }}>
        {FILTERS.map((x) => (
          <Tab key={x.key} value={x.key} label={`${x.label} (${data.filter(x.match).length})`} />
        ))}
      </Tabs>
      <Section title={f.label} pad={false}>
        {rows.length === 0 ? (
          <Empty title="Ninguna sucursal en esta vista"
            action={filter !== "all" && <Button onClick={() => setFilter("all")}>Ver todas</Button>}>
            Cambia de pestaña para ver las demás sucursales.
          </Empty>
        ) : (
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Router</TableCell>
                  <TableCell>Sucursal</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Último trabajo</TableCell>
                  <TableCell>LAN IPv4</TableCell>
                  <TableCell>Activa desde</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rows.map((s) => (
                  <TableRow key={s.id} hover>
                    <TableCell sx={{ fontWeight: 700 }}>{s.hostname}</TableCell>
                    <TableCell>
                      <Box component={Link} href={`/sites/detail/?id=${s.id}`}
                        sx={{ color: C.mora, fontWeight: 600, textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>
                        {s.name}
                      </Box>
                      <Box sx={{ color: "text.secondary", fontSize: 13, display: "flex", alignItems: "center", gap: 0.5 }}>
                        {s.code}
                        {s.protected && (
                          <Tooltip title="Configurada a mano antes del portal: no se puede dar de baja desde aquí">
                            <LockOutlined sx={{ fontSize: 14 }} aria-label="Protegida" />
                          </Tooltip>)}
                      </Box>
                    </TableCell>
                    <TableCell><SiteChip site={s} /></TableCell>
                    <TableCell>
                      {s.last_job ? (
                        <Box component={Link} href={`/jobs/detail/?id=${s.last_job.id}`}
                          sx={{ textDecoration: "none", color: "inherit", display: "flex", gap: 1, alignItems: "center" }}>
                          {JOB_TYPE[s.last_job.type]} <JobStatusChip status={s.last_job.status} />
                        </Box>
                      ) : <Box component="span" sx={{ color: "text.secondary" }}>Importada</Box>}
                    </TableCell>
                    <TableCell><Mono>{rule ? `10.${rule.D + s.site_number}.0.0/24` : "…"}</Mono></TableCell>
                    <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtDate(s.activated_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Section>
      {baja && <DecommissionDialog options={decommissionable(data)} onClose={() => setBaja(false)} />}
    </>
  );
}

export default function Page() {
  return <AppShell><Sites /></AppShell>;
}
