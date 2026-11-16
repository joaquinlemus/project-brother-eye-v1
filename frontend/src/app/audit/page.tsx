"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import { Fragment, useState } from "react";
import AppShell from "@/components/AppShell";
import { Empty, LoadError, Loading, Mono, PageHeader, Section } from "@/components/Page";
import { api, ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { C, mono } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

interface Entry {
  id: number; occurred_at: string; actor_type: string; actor: string | null; action: string; target_type: string;
  target_id: string; source_ip: string | null; before_state: unknown; after_state: unknown; outcome: string; row_hash: string;
}
const ACTION: Record<string, string> = {
  "site.create": "Alta solicitada", "site.activate": "Sucursal activada", "site.provision": "Alta fallida",
  "site.decommission": "Baja solicitada", "site.decommission.run": "Baja fallida", "site.retire": "Sucursal retirada",
  "site.import": "Sucursal importada", "job.retry": "Reintento", "ipam.release": "Cuarentena liberada",
  "auth.login": "Inicio de sesión", "auth.mfa": "Código MFA", "auth.mfa.enroll": "MFA activado",
  "auth.password": "Cambio de contraseña", "user.create": "Usuario creado", "user.update": "Usuario modificado",
  "user.reset_mfa": "MFA reiniciado", "user.password_reset": "Contraseña asignada",
  "monitoring.reconcile": "Comparación con Zabbix",
};
const OUTCOME: Record<string, [string, string]> = {
  SUCCESS: ["Correcto", C.pistacho], FAILURE: ["Falló", C.fresa], DENIED: ["Denegado", C.barquillo],
};
const FILTERS = [["", "Todo"], ["site.", "Sucursales"], ["job.", "Trabajos"], ["ipam.", "IPAM"],
  ["auth.", "Accesos"], ["user.", "Usuarios"], ["monitoring.", "Monitoreo"]];

function Audit() {
  const [f, setF] = useState("");
  const { data, error, reload } = useApi<Entry[]>(`/audit?limit=300${f ? `&action=${f}` : ""}`, 15000);
  const [open, setOpen] = useState<number | null>(null);
  const [check, setCheck] = useState<{ valid: boolean; checked: number; broken_at_id: number | null } | null>(null);
  const [checkErr, setCheckErr] = useState<string | null>(null);
  const verify = async () => {
    setCheckErr(null);
    try { setCheck(await api.get("/audit/verify")); } catch (e) { setCheckErr((e as ApiError).message); }
  };
  return (
    <>
      <PageHeader title="Auditoría"
        subtitle="Registro de solo inserción: cada entrada guarda el hash de la anterior, así que cualquier alteración rompe la cadena."
        actions={<Button variant="outlined" onClick={verify}>Verificar integridad</Button>} />
      {checkErr && <Alert severity="error" sx={{ mb: 2 }}>{checkErr}</Alert>}
      {check && (
        <Alert severity={check.valid ? "success" : "error"} onClose={() => setCheck(null)} sx={{ mb: 2 }}>
          {check.valid ? `Cadena íntegra: ${check.checked} entradas verificadas.`
            : `La cadena se rompe en la entrada ${check.broken_at_id}: el registro fue alterado.`}
        </Alert>)}
      <Section title="Entradas" pad={false}
        aside={<TextField select label="Mostrar" value={f} onChange={(e) => setF(e.target.value)} slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }} sx={{ width: 180 }}>
          {FILTERS.map(([k, l]) => <MenuItem key={k} value={k}>{l}</MenuItem>)}
        </TextField>}>
        {error ? <LoadError error={error} retry={reload} /> : !data ? <Loading /> : !data.length ? <Empty title="Sin entradas" /> : (
          <Box sx={{ overflowX: "auto" }}>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Fecha</TableCell><TableCell>Quién</TableCell><TableCell>Acción</TableCell>
                <TableCell>Resultado</TableCell><TableCell>IP de origen</TableCell><TableCell>Detalle</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {data.map((a) => (
                  <Fragment key={a.id}>
                    <TableRow hover>
                      <TableCell sx={{ whiteSpace: "nowrap" }}>{fmtDate(a.occurred_at)}</TableCell>
                      <TableCell>{a.actor ?? (a.actor_type === "RUNNER" ? "Ansible (worker)" : "Sistema")}</TableCell>
                      <TableCell>{ACTION[a.action] ?? a.action}</TableCell>
                      <TableCell sx={{ color: OUTCOME[a.outcome]?.[1], fontWeight: 600 }}>{OUTCOME[a.outcome]?.[0] ?? a.outcome}</TableCell>
                      <TableCell><Mono>{a.source_ip ?? "—"}</Mono></TableCell>
                      <TableCell>
                        <Button size="small" onClick={() => setOpen(open === a.id ? null : a.id)} aria-expanded={open === a.id}>
                          {open === a.id ? "Ocultar" : "Ver"}
                        </Button>
                      </TableCell>
                    </TableRow>
                    {open === a.id && (
                      <TableRow>
                        <TableCell colSpan={6} sx={{ background: C.wash }}>
                          <Box component="pre" sx={{ m: 0, fontFamily: mono, fontSize: 12, whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                            {JSON.stringify({ objetivo: `${a.target_type} ${a.target_id}`, antes: a.before_state,
                              despues: a.after_state, hash: a.row_hash }, null, 2)}
                          </Box>
                        </TableCell>
                      </TableRow>)}
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </Box>)}
      </Section>
    </>
  );
}

export default function Page() {
  return <AppShell><Audit /></AppShell>;
}
