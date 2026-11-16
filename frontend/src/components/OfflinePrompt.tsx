"use client";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import { api, ApiError, type OfflineAlert } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { useApi } from "@/lib/useApi";
import { DIALOG_TITLE_SX, ForgetForm } from "./ForgetDialog";

function duration(min: number) {
  if (min < 60) return `${min} min`;
  const h = Math.floor(min / 60);
  return `${h} h${min % 60 ? ` ${min % 60} min` : ""}`;
}

/**
 * Pregunta al administrador por las sucursales que no responden desde hace más del plazo
 * configurado (OFFLINE_PROMPT_MINUTES). Una a la vez; "Más tarde" la oculta hasta recargar.
 */
export default function OfflinePrompt() {
  const { data, reload } = useApi<{ threshold_minutes: number; sites: OfflineAlert[] }>(
    "/sites/offline-alerts", 60000);
  const [later, setLater] = useState<string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const a = data?.sites.find((x) => !later.includes(x.site_id));
  if (!a) return null;

  const keep = async () => {
    setBusy(true);
    setErr(null);
    try {
      await api.post(`/sites/${a.site_id}/offline-alert/keep`);
      await reload();
    } catch (e) {
      setErr((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };
  const close = () => { setLater((l) => [...l, a.site_id]); setConfirming(false); setErr(null); };

  return (
    <Dialog open onClose={busy ? undefined : close} maxWidth="sm" fullWidth aria-labelledby="offline-title">
      <DialogTitle id="offline-title" sx={DIALOG_TITLE_SX}>
        {a.hostname} no responde desde hace {duration(a.minutes_down)}
      </DialogTitle>
      {confirming ? (
        <ForgetForm target={{ id: a.site_id, code: a.code, name: a.name, hostname: a.hostname, since: a.since }}
          onCancel={() => setConfirming(false)} cancelLabel="Volver" />
      ) : (
        <>
          <DialogContent>
            <Typography sx={{ mb: 1.5 }}>
              La sucursal <b>{a.name}</b> ({a.code}) no responde al portal desde {fmtDate(a.since)}.
            </Typography>
            <Typography sx={{ mb: 1.5, fontWeight: 600 }}>¿Se eliminó esta sucursal?</Typography>
            <Typography variant="body2" color="text.secondary">
              Si respondes que sí, se retira del monitoreo y se liberan sus direcciones. Si sigue en servicio,
              el portal volverá a preguntar dentro de {duration(data!.threshold_minutes)} si todavía no responde.
            </Typography>
            {err && <Typography color="error" sx={{ mt: 1.5 }}>{err}</Typography>}
          </DialogContent>
          <DialogActions sx={{ px: 3, pb: 2.5, flexWrap: "wrap", gap: 1 }}>
            <Button onClick={close} disabled={busy}>Decidir más tarde</Button>
            <Button variant="outlined" onClick={keep} disabled={busy}>No, sigue en servicio</Button>
            <Button variant="contained" color="error" onClick={() => setConfirming(true)} disabled={busy}>
              Sí, retirar monitoreo
            </Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );
}
