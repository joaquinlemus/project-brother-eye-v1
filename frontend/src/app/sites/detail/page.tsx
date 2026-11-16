"use client";
import ArrowBack from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useEffect, useState } from "react";
import AppShell, { can, useMe } from "@/components/AppShell";
import DecommissionDialog from "@/components/DecommissionDialog";
import ForgetDialog from "@/components/ForgetDialog";
import JobsTable from "@/components/JobsTable";
import { LoadError, Loading, Mono, PageHeader, Section } from "@/components/Page";
import { AllocStatusChip, SiteChip, SnmpChip } from "@/components/Status";
import { api, ApiError, BASE_PATH, isUnreachable, type Allocation, type Job, type Site, type ZabbixHost } from "@/lib/api";
import { fmtDate, RESOURCE } from "@/lib/format";
import { C, mono } from "@/lib/theme";
import { useApi, useQueryParam } from "@/lib/useApi";

interface Detail extends Site {
  notes: string | null;
  allocations: Allocation[];
  jobs: Job[];
  zabbix: { state: string; zabbix_hostid: string | null; last_error: string | null; last_sync_at: string }[];
  events: { event_type: string; payload: Record<string, unknown>; occurred_at: string }[];
}

const EVENT: Record<string, string> = {
  SiteProvisioningRequested: "Alta solicitada",
  SiteActivated: "Sucursal activa",
  SiteProvisionFailed: "El alta falló",
  SiteDecommissionRequested: "Baja solicitada",
  SiteRetired: "Sucursal retirada",
  SiteDecommissionFailed: "La baja falló",
  SiteUnreachable: "Sin conectividad",
  SiteReachable: "Conectividad recuperada",
  SiteForgetRequested: "Retiro solicitado (router sin respuesta)",
};
const ZBX: Record<string, string> = {
  REGISTERED: "Registrado", PENDING: "Pendiente de verificar", DRIFT: "No aparece en Zabbix",
  REMOVED: "Eliminado", ERROR: "Error",
};

function VarsDialog({ siteId, onClose }: { siteId: string; onClose: () => void }) {
  const [text, setText] = useState<string | null>(null);
  useEffect(() => {
    fetch(`${BASE_PATH}/api/v1/sites/${siteId}/ansible-vars`, { credentials: "same-origin" })
      .then((r) => r.text()).then(setText).catch(() => setText("No se pudo cargar."));
  }, [siteId]);
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ fontFamily: '"Bricolage Grotesque Variable"', fontWeight: 700 }}>
        Variables que recibe Ansible
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          El worker escribe este archivo en inventories/ antes de llamar a run-job.sh.
        </Typography>
        <Box component="pre" sx={{ m: 0, p: 2, background: C.ink, color: "#E3E8EE", borderRadius: 1,
          fontFamily: mono, fontSize: 13, overflowX: "auto" }}>{text ?? "Cargando…"}</Box>
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}

function value(a: Allocation) {
  if (a.resource === "SITE_ID") return `${a.int_value} (R${a.int_value})`;
  if (["LAN_V4", "LAN_V6"].includes(a.resource)) return a.prefix;
  return a.ip;
}

function SiteDetail() {
  const me = useMe();
  const id = useQueryParam("id");
  const { data: s, error, reload } = useApi<Detail>(id ? `/sites/${id}` : null, 5000);
  const mon = useApi<{ hosts: ZabbixHost[] }>("/monitoring/hosts", 30000);
  const [dialog, setDialog] = useState<"baja" | "vars" | "retiro" | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  if (error) return <LoadError error={error} retry={reload} />;
  if (!s) return <Loading />;
  const busy = s.jobs.some((j) => j.status === "QUEUED" || j.status === "RUNNING");
  const canDecom = can(me, "site:decommission") && !s.protected && !busy &&
    ["ACTIVE", "PROVISION_FAILED", "DECOMMISSION_FAILED"].includes(s.status);
  const down = isUnreachable(s);
  const canForget = down && can(me, "site:forget") && !s.protected && !busy;
  const quarantined = s.allocations.some((a) => a.status === "QUARANTINED");
  const zhost = mon.data?.hosts.find((h) => h.host === s.hostname);
  const zdb = s.zabbix[0];

  const release = async () => {
    try {
      await api.post(`/sites/${s.id}/release-quarantine`);
      setMsg(`Recursos de ${s.hostname} liberados: el router ya se puede usar en una nueva alta.`);
      reload();
    } catch (e) {
      setMsg((e as ApiError).message);
    }
  };

  return (
    <>
      <PageHeader title={s.name}
        back={<Button component={Link} href="/sites/" startIcon={<ArrowBack />} sx={{ mb: 1, ml: -1 }}>Sucursales</Button>}
        subtitle={
          <Box component="span" sx={{ display: "inline-flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
            <span>Router <b>{s.hostname}</b></span><span>Código <b>{s.code}</b></span>
            <SiteChip site={s} />
          </Box>}
        actions={<>
          <Button variant="outlined" onClick={() => setDialog("vars")}>Ver variables de Ansible</Button>
          {s.status === "RETIRED" && quarantined && can(me, "ipam:release") && (
            <Button variant="outlined" onClick={release}>Liberar cuarentena</Button>)}
          {canForget && (
            <Button variant="contained" color="error" onClick={() => setDialog("retiro")}>Retirar sin conectar</Button>)}
          {canDecom && !down && <Button variant="contained" color="error" onClick={() => setDialog("baja")}>Dar de baja</Button>}
        </>} />

      {msg && <Alert severity="info" onClose={() => setMsg(null)} sx={{ mb: 2 }}>{msg}</Alert>}
      {s.protected && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Sucursal protegida: se configuró a mano antes del portal. Aparece en el inventario y en el monitoreo,
          pero el portal no permite darla de baja.
        </Alert>)}
      {down && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {s.hostname} no responde desde {fmtDate(s.reachability!.since)} (última prueba {fmtDate(s.reachability!.checked_at)}).
          {s.protected ? " Es una sucursal protegida: revisa el router en el laboratorio."
            : canForget ? " Si el router se eliminó, usa Retirar sin conectar: la baja normal necesita conectarse al router."
            : " Un administrador puede retirarla si el router ya no existe."}
        </Alert>)}
      {busy && (
        <Alert severity="warning" sx={{ mb: 2 }}
          action={<Button color="inherit" component={Link} href={`/jobs/detail/?id=${s.jobs[0].id}`}>Ver en vivo</Button>}>
          Hay un trabajo de Ansible en curso para esta sucursal.
        </Alert>)}

      <Box sx={{ display: "grid", gridTemplateColumns: { lg: "3fr 2fr" }, gap: 3 }}>
        <Section title="Direccionamiento (IPAM)" pad={false}>
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead><TableRow><TableCell>Recurso</TableCell><TableCell>Valor</TableCell><TableCell>Estado</TableCell></TableRow></TableHead>
              <TableBody>
                {s.allocations.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell>{RESOURCE[a.resource] ?? a.resource}</TableCell>
                    <TableCell><Mono>{value(a)}</Mono></TableCell>
                    <TableCell>
                      <AllocStatusChip status={a.status} />
                      {a.status === "QUARANTINED" && a.quarantine_until && (
                        <Typography variant="body2" color="text.secondary">hasta {fmtDate(a.quarantine_until)}</Typography>)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Section>
        <Box>
          <Section title="Monitoreo">
            {zhost ? (
              <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                <SnmpChip snmp={zhost.snmp} />
                <Typography variant="body2" color="text.secondary">
                  En Zabbix como <b>{zhost.name}</b>, SNMPv3 a <Mono>{zhost.ip}</Mono>
                </Typography>
                {zhost.snmp_error && <Typography variant="body2" color="error">{zhost.snmp_error}</Typography>}
                {zhost.problems.length > 0 ? zhost.problems.slice(0, 4).map((p, i) => (
                  <Typography key={i} variant="body2" sx={{ color: C.fresa }}>{p.name}</Typography>
                )) : <Typography variant="body2" color="text.secondary">Sin problemas activos.</Typography>}
              </Box>
            ) : (
              <Typography color="text.secondary">
                {s.status === "RETIRED" ? "El host se eliminó de Zabbix al dar de baja la sucursal."
                  : zdb ? `Estado en el inventario: ${ZBX[zdb.state] ?? zdb.state}.` : "Sin registro en Zabbix."}
                {zdb?.last_error && ` ${zdb.last_error}`}
              </Typography>
            )}
          </Section>
          <Section title="Historial">
            <Box component="ol" sx={{ m: 0, pl: 2.5, "& li": { mb: 1 } }}>
              {s.events.map((e, i) => (
                <li key={i}>
                  <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{EVENT[e.event_type] ?? e.event_type}</Typography>
                  <Typography variant="body2" color="text.secondary">{fmtDate(e.occurred_at)}</Typography>
                </li>
              ))}
              {s.imported && <li><Typography sx={{ fontSize: 14 }}>Importada al portal (existía antes)</Typography></li>}
            </Box>
          </Section>
        </Box>
      </Box>

      <Section title="Trabajos de Ansible" pad={false}>
        {s.jobs.length ? <JobsTable jobs={s.jobs} showSite={false} /> : (
          <Typography sx={{ p: 2.5 }} color="text.secondary">Esta sucursal no tiene trabajos: se importó ya configurada.</Typography>
        )}
      </Section>
      {dialog === "baja" && <DecommissionDialog site={s} onClose={() => setDialog(null)} />}
      {dialog === "retiro" && (
        <ForgetDialog target={{ ...s, since: s.reachability?.since ?? null }} onClose={() => setDialog(null)} />)}
      {dialog === "vars" && <VarsDialog siteId={s.id} onClose={() => setDialog(null)} />}
    </>
  );
}

export default function Page() {
  return <AppShell><SiteDetail /></AppShell>;
}
