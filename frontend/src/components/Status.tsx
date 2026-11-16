import Box from "@mui/material/Box";
import { isUnreachable, type JobStatus, type Site, type SiteStatus } from "@/lib/api";
import { ALLOC_STATUS, JOB_STATUS, SITE_STATUS } from "@/lib/format";
import { C } from "@/lib/theme";

const SITE_COLOR: Record<SiteStatus, string> = {
  ACTIVE: C.pistacho,
  PROVISIONING: C.barquillo,
  DECOMMISSIONING: C.barquillo,
  PROVISION_FAILED: C.fresa,
  DECOMMISSION_FAILED: C.fresa,
  RETIRED: C.vainilla,
};
const JOB_COLOR: Record<JobStatus, string> = {
  QUEUED: C.vainilla,
  RUNNING: C.barquillo,
  SUCCEEDED: C.pistacho,
  FAILED: C.fresa,
  CANCELLED: C.vainilla,
};
const ALLOC_COLOR: Record<string, string> = {
  RESERVED: C.barquillo,
  ALLOCATED: C.pistacho,
  QUARANTINED: C.mora,
  RELEASED: C.vainilla,
};

export const siteColor = (s: SiteStatus) => SITE_COLOR[s];

/** Color de la sucursal en el mapa: rojo si debería estar en servicio y no responde. */
export const siteMapColor = (s: Pick<Site, "status" | "reachability">) =>
  isUnreachable(s) ? C.fresa : SITE_COLOR[s.status];

/** Estado como "bola de helado": un círculo del color del sabor y el texto. */
function Scoop({ color, label, pulse }: { color: string; label: string; pulse?: boolean }) {
  return (
    <Box component="span" sx={{ display: "inline-flex", alignItems: "center", gap: 0.75, whiteSpace: "nowrap",
      fontSize: 13, fontWeight: 500, color: C.ink }}>
      <Box component="span" aria-hidden sx={{
        width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0,
        boxShadow: `0 0 0 3px ${color}22`,
        ...(pulse && { animation: "scoop 1.4s ease-in-out infinite",
          "@keyframes scoop": { "50%": { boxShadow: `0 0 0 6px ${color}10` } } }),
      }} />
      {label}
    </Box>
  );
}

export function SiteStatusChip({ status }: { status: SiteStatus }) {
  return <Scoop color={SITE_COLOR[status]} label={SITE_STATUS[status]}
    pulse={status === "PROVISIONING" || status === "DECOMMISSIONING"} />;
}

/** Estado de la sucursal teniendo en cuenta la conectividad: "No disponible" si no responde. */
export function SiteChip({ site }: { site: Pick<Site, "status" | "reachability"> }) {
  if (isUnreachable(site)) return <Scoop color={C.fresa} label="No disponible" pulse />;
  return <SiteStatusChip status={site.status} />;
}

export function JobStatusChip({ status }: { status: JobStatus }) {
  return <Scoop color={JOB_COLOR[status]} label={JOB_STATUS[status]} pulse={status === "RUNNING"} />;
}

export function AllocStatusChip({ status }: { status: string }) {
  return <Scoop color={ALLOC_COLOR[status] ?? C.vainilla} label={ALLOC_STATUS[status] ?? status} />;
}

export function SnmpChip({ snmp }: { snmp: string }) {
  const map: Record<string, [string, string]> = {
    AVAILABLE: [C.pistacho, "SNMP disponible"],
    UNAVAILABLE: [C.fresa, "SNMP sin respuesta"],
    UNKNOWN: [C.vainilla, "SNMP sin datos aún"],
    NONE: [C.vainilla, "Sin interfaz SNMP"],
  };
  const [c, l] = map[snmp] ?? map.UNKNOWN;
  return <Scoop color={c} label={l} />;
}
