import type { JobStatus, SiteStatus } from "./api";

const dtf = new Intl.DateTimeFormat("es-GT", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "America/Guatemala",
});

export function fmtDate(v: string | null | undefined): string {
  return v ? dtf.format(new Date(v)) : "—";
}

export function fmtDuration(a: string | null, b: string | null): string {
  if (!a) return "—";
  const ms = (b ? new Date(b) : new Date()).getTime() - new Date(a).getTime();
  const s = Math.max(0, Math.round(ms / 1000));
  return s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60} s`;
}

export function ago(v: string | null): string {
  if (!v) return "—";
  const s = Math.round((Date.now() - new Date(v).getTime()) / 1000);
  if (s < 60) return "hace un momento";
  if (s < 3600) return `hace ${Math.floor(s / 60)} min`;
  if (s < 86400) return `hace ${Math.floor(s / 3600)} h`;
  return fmtDate(v);
}

export const SITE_STATUS: Record<SiteStatus, string> = {
  PROVISIONING: "Aprovisionando",
  ACTIVE: "Activa",
  PROVISION_FAILED: "Alta con error",
  DECOMMISSIONING: "Dando de baja",
  DECOMMISSION_FAILED: "Baja con error",
  RETIRED: "Retirada",
};

export const JOB_STATUS: Record<JobStatus, string> = {
  QUEUED: "En cola",
  RUNNING: "Ejecutando",
  SUCCEEDED: "Completado",
  FAILED: "Falló",
  CANCELLED: "Cancelado",
};

export const JOB_TYPE: Record<string, string> = {
  PROVISION: "Alta", DECOMMISSION: "Baja", FORGET: "Retiro sin conexión",
};

export const ALLOC_STATUS: Record<string, string> = {
  RESERVED: "Reservado",
  ALLOCATED: "Asignado",
  QUARANTINED: "En cuarentena",
  RELEASED: "Liberado",
};

export const RESOURCE: Record<string, string> = {
  SITE_ID: "Site ID",
  UNDERLAY_V4: "Underlay (gestión)",
  LOOPBACK_V4: "Loopback0",
  LAN_V4: "LAN IPv4",
  LAN_V6: "LAN IPv6",
  TUNNEL1_V4: "Tunnel0 IPv4 (Hub 1)",
  TUNNEL1_V6: "Tunnel0 IPv6 (Hub 1)",
  TUNNEL2_V4: "Tunnel1 IPv4 (Hub 2)",
  TUNNEL2_V6: "Tunnel1 IPv6 (Hub 2)",
};

export const ROLE: Record<string, string> = {
  admin: "Administrador",
  netops: "Operador de red",
  auditor: "Auditor",
  viewer: "Lector",
};
