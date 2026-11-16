"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError, isUnreachable, type Site } from "@/lib/api";
import { mono } from "@/lib/theme";

type Target = Pick<Site, "id" | "code" | "name" | "hostname">;

const DECOMMISSIONABLE = ["ACTIVE", "PROVISION_FAILED", "DECOMMISSION_FAILED"];

/** Sucursales que se pueden dar de baja: no protegidas, que responden y sin un trabajo en curso. */
export function decommissionable(sites: Site[]): Site[] {
  return sites
    .filter((s) => !s.protected && DECOMMISSIONABLE.includes(s.status) && !isUnreachable(s) &&
      !(s.last_job && (s.last_job.status === "QUEUED" || s.last_job.status === "RUNNING")))
    .sort((a, b) => a.site_number - b.site_number);
}

/**
 * Confirmación de baja. Con `site` la sucursal ya viene elegida (página de detalle);
 * con `options` primero se elige de la lista (botón "Dar de baja una sucursal").
 */
export default function DecommissionDialog({ site, options, onClose }:
  { site?: Target; options?: Target[]; onClose: () => void }) {
  const router = useRouter();
  const [selectedId, setSelectedId] = useState(site?.id ?? "");
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const target = site ?? options?.find((o) => o.id === selectedId);

  const go = async () => {
    if (!target) return;
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<{ job: { id: string } }>(`/sites/${target.id}/decommission`,
        { confirm_code: code, reason: reason.trim() });
      router.push(`/jobs/detail/?id=${r.job.id}`);
    } catch (e) {
      setErr((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <Dialog open onClose={busy ? undefined : onClose} maxWidth="sm" fullWidth aria-labelledby="baja-title">
      <DialogTitle id="baja-title" sx={{ fontFamily: '"Bricolage Grotesque Variable"', fontWeight: 700 }}>
        {target && site ? `Dar de baja ${target.hostname}, ${target.name}` : "Dar de baja una sucursal"}
      </DialogTitle>
      <DialogContent>
        {!site && (
          options && options.length > 0 ? (
            <TextField select label="Sucursal" value={selectedId} autoFocus sx={{ mt: 1, mb: 2.5 }}
              onChange={(e) => { setSelectedId(e.target.value); setCode(""); }}>
              {options.map((o) => (
                <MenuItem key={o.id} value={o.id}>{o.hostname}, {o.name} ({o.code})</MenuItem>
              ))}
            </TextField>
          ) : (
            <Alert severity="info" sx={{ mb: 2 }}>
              No hay sucursales que se puedan dar de baja: las protegidas, las que no responden y las que
              tienen un trabajo en curso no aparecen en la lista.
            </Alert>
          )
        )}
        <Typography sx={{ mb: 1.5 }}>Ansible quitará del router y de la red:</Typography>
        <Box component="ul" sx={{ mt: 0, mb: 2, pl: 2.5, color: "text.secondary", "& li": { mb: 0.25 } }}>
          <li>los túneles DMVPN hacia los dos hubs y el perfil IPsec IKEv2,</li>
          <li>OSPFv2 y OSPFv3, la Loopback0 y la LAN IPv4/IPv6,</li>
          <li>SNMPv3 y el host en Zabbix.</li>
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          Las direcciones quedan en cuarentena y el historial se conserva. El acceso de gestión se mantiene.
        </Typography>
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        {target && (
          <>
            <TextField label={`Escribe ${target.code} para confirmar`} value={code} autoFocus={!!site}
              onChange={(e) => setCode(e.target.value.toUpperCase())} sx={{ mb: 2 }}
              slotProps={{ htmlInput: { style: { fontFamily: mono } } }} />
            <TextField label="Motivo" value={reason} multiline minRows={2} onChange={(e) => setReason(e.target.value)}
              helperText="Queda en la auditoría. Ejemplo: cierre de la sucursal" />
          </>
        )}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose} disabled={busy}>Cancelar</Button>
        <Button variant="contained" color="error" onClick={go}
          disabled={busy || !target || code !== target.code || reason.trim().length < 3}>
          {busy ? "Creando trabajo…" : target ? `Dar de baja ${target.hostname}` : "Dar de baja"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
