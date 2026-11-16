"use client";
import AddIcon from "@mui/icons-material/Add";
import RemoveCircleOutline from "@mui/icons-material/RemoveCircleOutline";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useState } from "react";
import AppShell, { can, useMe } from "@/components/AppShell";
import DecommissionDialog, { decommissionable } from "@/components/DecommissionDialog";
import JobsTable from "@/components/JobsTable";
import { Empty, LoadError, Loading, PageHeader, Section } from "@/components/Page";
import Topology from "@/components/Topology";
import { isUnreachable, type Job, type Site, type ZabbixHost } from "@/lib/api";
import { useApi } from "@/lib/useApi";
import { C } from "@/lib/theme";

interface Dash {
  sites: Record<string, number>;
  recent_jobs: Job[];
  worker: { alive: boolean; last_seen_s: number | null };
  zabbix_configured: boolean;
}
interface Mon { configured: boolean; hosts: ZabbixHost[]; error: string | null }

function Signal({ ok, label, detail }: { ok: boolean | null; label: string; detail: string }) {
  const color = ok === null ? C.vainilla : ok ? C.pistacho : C.fresa;
  return (
    <Box sx={{ display: "flex", gap: 1.25, alignItems: "flex-start" }}>
      <Box sx={{ width: 10, height: 10, borderRadius: "50%", background: color, mt: 0.75, flexShrink: 0 }} />
      <Box>
        <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{label}</Typography>
        <Typography sx={{ color: "text.secondary", fontSize: 13 }}>{detail}</Typography>
      </Box>
    </Box>
  );
}

function Dashboard() {
  const me = useMe();
  const dash = useApi<Dash>("/dashboard", 5000);
  const sites = useApi<Site[]>("/sites", 5000);
  const mon = useApi<Mon>("/monitoring/hosts", 30000);
  const [baja, setBaja] = useState(false);
  if (dash.error) return <LoadError error={dash.error} retry={dash.reload} />;
  if (!dash.data || !sites.data) return <Loading />;
  const n = dash.data.sites;
  const active = n.ACTIVE ?? 0;
  const busy = (n.PROVISIONING ?? 0) + (n.DECOMMISSIONING ?? 0);
  const failed = (n.PROVISION_FAILED ?? 0) + (n.DECOMMISSION_FAILED ?? 0);
  const down = sites.data.filter(isUnreachable).length;
  const w = dash.data.worker;
  const m = mon.data;

  return (
    <>
      <PageHeader title="Red de sucursales"
        subtitle={`${active} ${active === 1 ? "sucursal activa" : "sucursales activas"}` +
          (down ? `, ${down} sin conectividad` : "") +
          (busy ? `, ${busy} en proceso` : "") + (failed ? `, ${failed} con error que requiere atención` : "") + "."}
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

      <Box sx={{ display: "grid", gridTemplateColumns: { sm: "1fr 1fr" }, gap: 2.5, mb: 3 }}>
        <Signal ok={w.alive} label={w.alive ? "Motor de Ansible listo" : "Motor de Ansible sin señal"}
          detail={w.alive ? "Los trabajos se ejecutan en orden, uno a la vez."
            : w.last_seen_s === null ? "El servicio de ejecución no ha arrancado. Avisa al administrador."
            : `Última señal hace ${w.last_seen_s} s. Avisa al administrador.`} />
        <Signal ok={!m ? null : !m.configured ? null : !m.error}
          label={!m ? "Consultando Zabbix…" : !m.configured ? "Zabbix sin configurar" : m.error ? "Zabbix no responde" : "Zabbix conectado"}
          detail={!m ? "" : !m.configured ? "El monitoreo no está conectado al portal."
            : m.error ?? `${m.hosts.filter((h) => h.snmp === "AVAILABLE").length} de ${m.hosts.length} routers responden por SNMP.`} />
      </Box>

      <Section title="Topología DMVPN" pad={false}>
        <Topology sites={sites.data} hosts={m?.hosts ?? []} />
      </Section>

      <Section title="Últimos trabajos" pad={false}
        aside={<Button component={Link} href="/jobs/" size="small">Ver todos</Button>}>
        {dash.data.recent_jobs.length ? <JobsTable jobs={dash.data.recent_jobs} /> : (
          <Empty title="Todavía no hay trabajos">
            Cada alta o baja crea un trabajo de Ansible que podrás seguir en vivo.
          </Empty>
        )}
      </Section>
      {baja && <DecommissionDialog options={decommissionable(sites.data)} onClose={() => setBaja(false)} />}
    </>
  );
}

export default function Page() {
  return <AppShell><Dashboard /></AppShell>;
}
