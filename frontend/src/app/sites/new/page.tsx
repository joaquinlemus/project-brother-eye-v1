"use client";
import ArrowBack from "@mui/icons-material/ArrowBack";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import AppShell from "@/components/AppShell";
import { LoadError, Loading, Mono, PageHeader } from "@/components/Page";
import { derive, type Rule } from "@/lib/addressing";
import { api, ApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { C } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

interface Avail {
  min: number;
  max: number;
  suggested: number | null;
  free: number[];
  free_count: number;
  quarantined: { site_number: number; hostname: string; until: string; site_code: string }[];
}

function NewSite() {
  const router = useRouter();
  const avail = useApi<Avail>("/sites/available-ids");
  const pools = useApi<{ rule: Rule }>("/ipam/pools");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [sid, setSid] = useState<number | "">("");
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (avail.data?.suggested && sid === "") setSid(avail.data.suggested);
  }, [avail.data, sid]);

  if (avail.error) return <LoadError error={avail.error} retry={avail.reload} />;
  if (!avail.data || !pools.data) return <Loading />;
  const a = avail.data;
  const rule = pools.data.rule;
  const codeErr = code && !/^[A-Z0-9-]{3,16}$/.test(code)
    ? "Usa de 3 a 16 letras sin tildes, números o guiones." : null;
  const nameErr = name && name.trim().length < 3 ? "Escribe al menos 3 caracteres." : null;
  const ready = !codeErr && !nameErr && code && name.trim() && sid !== "";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<{ job: { id: string } }>("/sites", { code, name: name.trim(), site_number: sid });
      router.push(`/jobs/detail/?id=${r.job.id}`);
    } catch (err) {
      setError(err as ApiError);
      setBusy(false);
      avail.reload();
    }
  };

  return (
    <>
      <PageHeader title="Dar de alta una sucursal"
        subtitle="El portal reserva los recursos en el IPAM, genera las variables y Ansible configura el router completo. Después se registra en Zabbix."
        back={<Button component={Link} href="/sites/" startIcon={<ArrowBack />} sx={{ mb: 1, ml: -1 }}>Sucursales</Button>} />
      {a.free_count === 0 ? (
        <Alert severity="warning">
          No quedan routers libres entre R{a.min} y R{a.max}. Libera la cuarentena de una sucursal retirada desde IPAM.
        </Alert>
      ) : (
        <Box component="form" onSubmit={submit} noValidate
          sx={{ display: "grid", gridTemplateColumns: { md: "minmax(0, 5fr) minmax(0, 6fr)" }, gap: 4, alignItems: "start" }}>
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
            {error && (
              <Alert severity="error">
                {error.message}
                {error.fields?.map((f) => <div key={f.field}>{f.field}: {f.message}</div>)}
              </Alert>
            )}
            <TextField label="Nombre de la sucursal" value={name} required
              onChange={(e) => setName(e.target.value)} onBlur={() => setTouched({ ...touched, name: true })}
              error={!!(touched.name && nameErr)}
              helperText={(touched.name && nameErr) || "Aparece en el portal y en Zabbix. Ejemplo: Heladería Zona 10"} />
            <TextField label="Código" value={code} required
              onChange={(e) => setCode(e.target.value.toUpperCase().replace(/\s/g, "-"))}
              onBlur={() => setTouched({ ...touched, code: true })}
              error={!!(touched.code && codeErr)}
              helperText={(touched.code && codeErr) || "Identificador corto y único, por ejemplo Z10. No se reutiliza."} />
            <TextField select label="Router del laboratorio" value={sid} required
              onChange={(e) => setSid(Number(e.target.value))}
              helperText={`Debe tener la configuración day-0 y responder por SSH en 172.16.0.${sid || "s"}.`}>
              {a.free.map((s) => (
                <MenuItem key={s} value={s}>R{s}{s === a.suggested ? " (primer libre)" : ""}</MenuItem>
              ))}
            </TextField>
            {a.quarantined.length > 0 && (
              <Typography variant="body2" color="text.secondary">
                En cuarentena: {a.quarantined.map((q) => `${q.hostname} (${q.site_code}) hasta ${fmtDate(q.until)}`).join("; ")}.
              </Typography>
            )}
            <Box>
              <Button type="submit" variant="contained" size="large" disabled={!ready || busy}>
                {busy ? "Reservando recursos…" : sid ? `Dar de alta R${sid}` : "Dar de alta"}
              </Button>
            </Box>
          </Box>
          <Box sx={{ border: `1px solid ${C.line}`, borderRadius: 1.5, background: C.paper }}>
            <Box sx={{ px: 2.5, pt: 2, pb: 1 }}>
              <Typography variant="h3">Direccionamiento que se reservará</Typography>
              <Typography variant="body2" color="text.secondary">
                Regla del equipo: D = {rule.D}, MMDD = {rule.MMDD}.
              </Typography>
            </Box>
            {sid !== "" && (
              <Table size="small">
                <TableBody>
                  {derive(sid, rule).map(([k, v]) => (
                    <TableRow key={k}>
                      <TableCell sx={{ color: "text.secondary", width: "42%" }}>{k}</TableCell>
                      <TableCell><Mono>{v}</Mono></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Box>
        </Box>
      )}
    </>
  );
}

export default function Page() {
  return <AppShell><NewSite /></AppShell>;
}
