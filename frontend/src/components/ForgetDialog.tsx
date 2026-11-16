"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { mono } from "@/lib/theme";

export interface ForgetTarget { id: string; code: string; name: string; hostname: string; since: string | null }

const TITLE = { fontFamily: '"Bricolage Grotesque Variable"', fontWeight: 700 } as const;

/** Lo que hace el retiro sin conexión; se repite en la pregunta automática y en el detalle. */
export function ForgetExplanation() {
  return (
    <>
      <Typography sx={{ mb: 1 }}>Ansible no se conectará al router. Solo hará esto:</Typography>
      <Box component="ul" sx={{ mt: 0, mb: 1.5, pl: 2.5, color: "text.secondary", "& li": { mb: 0.25 } }}>
        <li>eliminar el host de Zabbix,</li>
        <li>limpiar el registro NHRP de la sucursal en los dos hubs.</li>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        La sucursal pasa a Retirada, sus direcciones quedan en cuarentena y el historial se conserva. Si el
        router vuelve a aparecer, todavía tiene su configuración: bórrala antes de reutilizarlo.
      </Typography>
    </>
  );
}

/** Confirmación del retiro: escribir el código, igual que en la baja normal. */
export function ForgetForm({ target, onCancel, cancelLabel = "Cancelar" }:
  { target: ForgetTarget; onCancel: () => void; cancelLabel?: string }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [reason, setReason] = useState("El router se eliminó del laboratorio");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const go = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await api.post<{ job: { id: string } }>(`/sites/${target.id}/forget`,
        { confirm_code: code, reason: reason.trim() });
      router.push(`/jobs/detail/?id=${r.job.id}`);
    } catch (e) {
      setErr((e as ApiError).message);
      setBusy(false);
    }
  };

  return (
    <>
      <DialogContent>
        <ForgetExplanation />
        {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
        <TextField label={`Escribe ${target.code} para confirmar`} value={code} autoFocus
          onChange={(e) => setCode(e.target.value.toUpperCase())} sx={{ mb: 2 }}
          slotProps={{ htmlInput: { style: { fontFamily: mono } } }} />
        <TextField label="Motivo" value={reason} multiline minRows={2} onChange={(e) => setReason(e.target.value)}
          helperText="Queda en la auditoría" />
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onCancel} disabled={busy}>{cancelLabel}</Button>
        <Button variant="contained" color="error" onClick={go}
          disabled={busy || code !== target.code || reason.trim().length < 3}>
          {busy ? "Creando trabajo…" : `Retirar ${target.hostname}`}
        </Button>
      </DialogActions>
    </>
  );
}

/** Desde el detalle de la sucursal. */
export default function ForgetDialog({ target, onClose }: { target: ForgetTarget; onClose: () => void }) {
  return (
    <Dialog open onClose={onClose} maxWidth="sm" fullWidth aria-labelledby="forget-title">
      <DialogTitle id="forget-title" sx={TITLE}>Retirar {target.hostname}, {target.name}</DialogTitle>
      {target.since && (
        <Typography color="text.secondary" sx={{ px: 3, mt: -1, mb: 1 }}>
          Sin conectividad desde {fmtDate(target.since)}.
        </Typography>)}
      <ForgetForm target={target} onCancel={onClose} />
    </Dialog>
  );
}

export { TITLE as DIALOG_TITLE_SX };
