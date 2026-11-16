"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import AppShell, { can, useMe } from "@/components/AppShell";
import { Empty, LoadError, Loading, Mono, PageHeader, Section } from "@/components/Page";
import { SnmpChip } from "@/components/Status";
import { api, ApiError, type ZabbixHost } from "@/lib/api";
import { C } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

interface Mon { configured: boolean; hosts: ZabbixHost[]; error: string | null }
interface Rec { ok: string[]; missing_in_zabbix: string[]; unmanaged_in_zabbix: string[] }
const SEV = ["Sin clasificar", "Información", "Advertencia", "Media", "Alta", "Desastre"];

function Monitoring() {
  const me = useMe();
  const { data, error, reload } = useApi<Mon>("/monitoring/hosts", 30000);
  const [rec, setRec] = useState<Rec | null>(null);
  const [recErr, setRecErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (error) return <LoadError error={error} retry={reload} />;
  if (!data) return <Loading label="Consultando Zabbix…" />;

  const reconcile = async () => {
    setBusy(true);
    setRecErr(null);
    try {
      setRec(await api.post<Rec>("/monitoring/reconcile"));
    } catch (e) {
      setRecErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Monitoreo"
        subtitle="Estado en Zabbix de los routers que gestiona el portal. Zabbix los consulta por SNMPv3 en la VRF INET."
        actions={data.configured && can(me, "monitoring:reconcile") && (
          <Button variant="outlined" onClick={reconcile} disabled={busy}>
            {busy ? "Comparando…" : "Comparar inventario con Zabbix"}
          </Button>)} />
      {!data.configured && (
        <Alert severity="info" sx={{ mb: 2 }}>
          El monitoreo no está conectado al portal. Un administrador debe configurar el acceso a Zabbix.
        </Alert>)}
      {data.error && <Alert severity="error" sx={{ mb: 2 }}>{data.error}</Alert>}
      {recErr && <Alert severity="error" sx={{ mb: 2 }}>{recErr}</Alert>}
      {rec && (
        <Alert severity={rec.missing_in_zabbix.length ? "warning" : "success"} onClose={() => setRec(null)} sx={{ mb: 2 }}>
          {rec.missing_in_zabbix.length
            ? `Faltan en Zabbix: ${rec.missing_in_zabbix.join(", ")}. Vuelve a ejecutar el alta para registrarlos.`
            : `Inventario y Zabbix coinciden (${rec.ok.length} routers).`}
          {rec.unmanaged_in_zabbix.length > 0 && ` En Zabbix pero no en el portal: ${rec.unmanaged_in_zabbix.join(", ")}.`}
        </Alert>)}
      {data.configured && (
        <Section title="Routers en Zabbix" pad={false}>
          {!data.hosts.length ? <Empty title="Zabbix no tiene routers del portal">
            Los hosts aparecen aquí cuando Ansible los registra con la etiqueta gestionado_por = portal-xyz.
          </Empty> : (
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell>Router</TableCell><TableCell>Nombre en Zabbix</TableCell><TableCell>IP SNMP</TableCell>
                  <TableCell>Disponibilidad</TableCell><TableCell>Problemas activos</TableCell>
                </TableRow></TableHead>
                <TableBody>
                  {data.hosts.map((h) => (
                    <TableRow key={h.hostid}>
                      <TableCell sx={{ fontWeight: 700 }}>{h.host}</TableCell>
                      <TableCell>{h.name}{!h.enabled && <Typography variant="body2" color="text.secondary">Deshabilitado</Typography>}</TableCell>
                      <TableCell><Mono>{h.ip}</Mono></TableCell>
                      <TableCell>
                        <SnmpChip snmp={h.snmp} />
                        {h.snmp_error && <Typography variant="body2" color="text.secondary">{h.snmp_error}</Typography>}
                      </TableCell>
                      <TableCell>
                        {h.problems.length === 0 ? <Box component="span" sx={{ color: "text.secondary" }}>Ninguno</Box> :
                          h.problems.slice(0, 3).map((p, i) => (
                            <Typography key={i} variant="body2" sx={{ color: p.severity >= 3 ? C.fresa : C.ink }}>
                              {SEV[p.severity]}: {p.name}
                            </Typography>))}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>)}
        </Section>)}
    </>
  );
}

export default function Page() {
  return <AppShell><Monitoring /></AppShell>;
}
