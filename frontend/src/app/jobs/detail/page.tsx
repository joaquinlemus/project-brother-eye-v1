"use client";
import ArrowBack from "@mui/icons-material/ArrowBack";
import CheckCircle from "@mui/icons-material/CheckCircle";
import ErrorIcon from "@mui/icons-material/Error";
import RadioButtonUnchecked from "@mui/icons-material/RadioButtonUnchecked";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import FormControlLabel from "@mui/material/FormControlLabel";
import Switch from "@mui/material/Switch";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import AppShell, { can, useMe } from "@/components/AppShell";
import { LoadError, Loading, PageHeader, Section } from "@/components/Page";
import { JobStatusChip } from "@/components/Status";
import { api, ApiError, type Job, type Step } from "@/lib/api";
import { fmtDate, fmtDuration, JOB_TYPE } from "@/lib/format";
import { C, mono } from "@/lib/theme";
import { useApi, useQueryParam } from "@/lib/useApi";

const PLAN: Record<string, [string, string][]> = {
  PROVISION: [
    ["_probe", "Conectividad SSH"], ["fvrf", "VRF de gestión (INET)"],
    ["base", "Configuración base, AAA, NTP, syslog"], ["crypto_ikev2", "IPsec IKEv2"],
    ["lan", "Loopback y LAN IPv4/IPv6"], ["dmvpn_spoke", "Túneles DMVPN (Hub 1 y Hub 2)"],
    ["routing", "OSPFv2 y OSPFv3"], ["snmpv3", "SNMPv3"], ["_save", "Guardar configuración"],
    ["verify", "Verificación (IKEv2, NHRP, OSPF)"], ["zabbix_host", "Monitoreo en Zabbix"],
  ],
  DECOMMISSION: [
    ["zabbix_host", "Monitoreo en Zabbix"], ["decommission", "Retiro de configuración"],
    ["_hubs", "Verificación en los hubs"],
  ],
  FORGET: [
    ["zabbix_host", "Monitoreo en Zabbix"], ["_hubs", "Limpieza y verificación en los hubs"],
  ],
};

interface JobDetail extends Job { results: unknown[] }
interface LogChunk { offset: number; text: string; done: boolean; status: Job["status"]; steps: Step[] }

function StepIcon({ status }: { status?: string }) {
  if (status === "SUCCEEDED") return <CheckCircle sx={{ color: C.pistacho, fontSize: 22 }} />;
  if (status === "FAILED") return <ErrorIcon sx={{ color: C.fresa, fontSize: 22 }} />;
  if (status === "RUNNING") return <CircularProgress size={18} thickness={6} sx={{ color: C.barquillo, m: "2px" }} />;
  return <RadioButtonUnchecked sx={{ color: C.line, fontSize: 22 }} />;
}

function JobDetailView() {
  const me = useMe();
  const router = useRouter();
  const id = useQueryParam("id");
  const job = useApi<JobDetail>(id ? `/jobs/${id}` : null);
  const [log, setLog] = useState("");
  const [steps, setSteps] = useState<Step[]>([]);
  const [status, setStatus] = useState<Job["status"] | null>(null);
  const [follow, setFollow] = useState(true);
  const [retryErr, setRetryErr] = useState<string | null>(null);
  const offset = useRef(0);
  const box = useRef<HTMLPreElement>(null);
  const reloadJob = job.reload;

  useEffect(() => {
    if (!id) return;
    let stop = false;
    offset.current = 0;
    setLog("");
    const tick = async () => {
      try {
        const r = await api.get<LogChunk>(`/jobs/${id}/log?offset=${offset.current}`);
        if (stop) return;
        if (r.text) setLog((l) => l + r.text);
        offset.current = r.offset;
        setSteps(r.steps);
        setStatus((prev) => {
          if (prev && prev !== r.status) reloadJob();
          return r.status;
        });
        if (!r.done) setTimeout(tick, r.text ? 400 : 1500);
        else reloadJob();
      } catch {
        if (!stop) setTimeout(tick, 4000);
      }
    };
    tick();
    return () => { stop = true; };
  }, [id, reloadJob]);

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [log, follow]);

  if (job.error) return <LoadError error={job.error} retry={job.reload} />;
  if (!job.data) return <Loading />;
  const j = job.data;
  const st = status ?? j.status;
  const running = st === "RUNNING" || st === "QUEUED";
  const seen = new Map(steps.map((s) => [s.step, s]));
  const plan = PLAN[j.type] ?? [];
  const extra = steps.filter((s) => !plan.some(([k]) => k === s.step));

  const retry = async () => {
    setRetryErr(null);
    try {
      const r = await api.post<{ job: { id: string } }>(`/jobs/${j.id}/retry`);
      router.push(`/jobs/detail/?id=${r.job.id}`);
    } catch (e) {
      setRetryErr((e as ApiError).message);
    }
  };

  return (
    <>
      <PageHeader title={`${JOB_TYPE[j.type]} de R${j.site_number}`}
        back={<Button component={Link} href={`/sites/detail/?id=${j.site_id}`} startIcon={<ArrowBack />}
          sx={{ mb: 1, ml: -1 }}>{j.site_name}</Button>}
        subtitle={
          <Box component="span" sx={{ display: "inline-flex", gap: 2, flexWrap: "wrap", alignItems: "center" }}>
            <JobStatusChip status={st} />
            <span>Solicitado por <b>{j.requested_by_username}</b></span>
            <span>{fmtDate(j.created_at)}</span>
            {j.started_at && <span>Duración {fmtDuration(j.started_at, j.finished_at)}</span>}
            {j.attempt > 1 && <span>Intento {j.attempt}</span>}
          </Box>}
        actions={st === "FAILED" && can(me, "job:retry") && (
          <Button variant="contained" onClick={retry}>Reintentar</Button>)} />

      {retryErr && <Alert severity="error" sx={{ mb: 2 }}>{retryErr}</Alert>}
      {st === "QUEUED" && <Alert severity="info" sx={{ mb: 2 }}>En cola: empieza cuando termine el trabajo anterior.</Alert>}
      {st === "FAILED" && j.error_summary && (
        <Alert severity="error" sx={{ mb: 2, "& .MuiAlert-message": { minWidth: 0 } }}>
          <Typography sx={{ fontWeight: 600, mb: 0.5 }}>No se completó</Typography>
          <Box sx={{ fontFamily: mono, fontSize: 13, wordBreak: "break-word" }}>{j.error_summary}</Box>
          <Typography variant="body2" sx={{ mt: 1 }}>
            Corrige la causa y usa Reintentar. Ansible es idempotente: lo que ya quedó configurado no se repite.
          </Typography>
        </Alert>)}
      {st === "SUCCEEDED" && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {j.type === "PROVISION"
            ? `R${j.site_number} quedó configurado, verificado y registrado en Zabbix.`
            : j.type === "FORGET"
              ? `R${j.site_number} quedó fuera de Zabbix y de los hubs, y sus direcciones en cuarentena. El router no se tocó.`
              : `R${j.site_number} quedó limpio, fuera de Zabbix, y sus direcciones en cuarentena.`}
        </Alert>)}

      <Box sx={{ display: "grid", gridTemplateColumns: { lg: "minmax(260px, 2fr) 5fr" }, gap: 3, alignItems: "start" }}>
        <Section title="Pasos">
          <Box component="ol" sx={{ listStyle: "none", m: 0, p: 0 }}>
            {[...plan.map(([k, label]) => ({ k, label })), ...extra.map((s) => ({ k: s.step, label: s.label }))]
              .map(({ k, label }, i) => {
                const s = seen.get(k);
                const stepStatus = s ? (s.status === "RUNNING" && !running ? "FAILED" : s.status) : undefined;
                return (
                  <Box component="li" key={k} sx={{ display: "flex", gap: 1.25, py: 0.75, alignItems: "flex-start" }}>
                    <StepIcon status={stepStatus} />
                    <Box>
                      <Typography sx={{ fontSize: 14, fontWeight: s ? 600 : 400, color: s ? C.ink : C.inkSoft }}>
                        {i + 1}. {label}
                      </Typography>
                      {s && <Typography variant="body2" color="text.secondary">
                        {s.tasks} {s.tasks === 1 ? "tarea" : "tareas"}{s.changed ? ", con cambios" : ", sin cambios"}
                      </Typography>}
                    </Box>
                  </Box>
                );
              })}
          </Box>
        </Section>
        <Section title="Salida de Ansible" pad={false}
          aside={<FormControlLabel control={<Switch size="small" checked={follow} onChange={(e) => setFollow(e.target.checked)} />}
            label="Seguir al final" sx={{ mr: 0, "& .MuiTypography-root": { fontSize: 13 } }} />}>
          <Box component="pre" ref={box} tabIndex={0} aria-label="Salida de Ansible"
            sx={{ m: 0, p: 2, height: { xs: 360, lg: 560 }, overflow: "auto", background: C.ink, color: "#DCE3EA",
              fontFamily: mono, fontSize: 12.5, lineHeight: 1.55, whiteSpace: "pre-wrap", wordBreak: "break-word",
              "&:focus-visible": { outlineOffset: -2 } }}>
            {log ? colorize(log) : st === "QUEUED" ? "Esperando turno…" : "Sin salida todavía."}
          </Box>
        </Section>
      </Box>
    </>
  );
}

/** Colorea solo el inicio de las líneas de resultado; el resto queda como texto. */
function colorize(text: string) {
  return text.split("\n").map((line, i) => {
    const m = /^(ok|changed|fatal|failed|skipping|unreachable)(:)/.exec(line);
    const color = !m ? undefined : { ok: "#9CC98A", changed: "#E5B65C", skipping: "#8896A5" }[m[1]] ?? "#F08A95";
    const head = /^(TASK|PLAY|PLAY RECAP) \[?/.test(line);
    return (
      <span key={i} style={{ color: head ? "#FFFFFF" : color, fontWeight: head ? 600 : undefined }}>
        {line}{"\n"}
      </span>
    );
  });
}

export default function Page() {
  return <AppShell><JobDetailView /></AppShell>;
}
