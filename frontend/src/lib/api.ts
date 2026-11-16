// Cliente de la API. La sesión viaja en una cookie HttpOnly; las escrituras llevan la
// cabecera anti-CSRF. Un 401 manda al login.
export const BASE_PATH = "/portal_heladeria";
const API = `${BASE_PATH}/api/v1`;

export class ApiError extends Error {
  status: number;
  fields?: { field: string; message: string }[];
  constructor(status: number, message: string, fields?: { field: string; message: string }[]) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-Portal-CSRF"] = "1";
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      method,
      headers,
      credentials: "same-origin",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "No hay conexión con el portal. Revisa tu red e intenta de nuevo.");
  }
  if (res.status === 401 && !path.startsWith("/auth/")) {
    window.location.href = `${BASE_PATH}/login/`;
    throw new ApiError(401, "Tu sesión expiró. Vuelve a iniciar sesión.");
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") ?? "";
  const data = ct.includes("json") ? await res.json() : await res.text();
  if (!res.ok) {
    const detail = typeof data === "object" && data?.detail ? data.detail : `Error ${res.status}`;
    throw new ApiError(res.status, String(detail), data?.fields);
  }
  return data as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, body?: unknown) => request<T>("POST", p, body ?? {}),
  patch: <T>(p: string, body: unknown) => request<T>("PATCH", p, body),
};

// ----------------------------------------------------------------- tipos
export type SiteStatus =
  | "PROVISIONING"
  | "ACTIVE"
  | "PROVISION_FAILED"
  | "DECOMMISSIONING"
  | "DECOMMISSION_FAILED"
  | "RETIRED";
export type JobStatus = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";

export interface JobRef { id: string; type: string; status: JobStatus }

export interface Site {
  id: string;
  code: string;
  name: string;
  status: SiteStatus;
  site_number: number;
  hostname: string;
  protected: boolean;
  imported: boolean;
  created_at: string;
  activated_at: string | null;
  retired_at: string | null;
  created_by: string | null;
  last_job: JobRef | null;
  /** Prueba de conectividad del worker (TCP/ICMP a la IP underlay). null = sin datos aún. */
  reachability: { state: "REACHABLE" | "UNREACHABLE"; since: string; checked_at: string } | null;
}

/** Sin conectividad mientras la sucursal debería estar en servicio. */
export const isUnreachable = (s: Pick<Site, "status" | "reachability">) =>
  s.reachability?.state === "UNREACHABLE" && (s.status === "ACTIVE" || s.status === "DECOMMISSION_FAILED");

export interface OfflineAlert {
  site_id: string;
  code: string;
  name: string;
  hostname: string;
  since: string;
  checked_at: string;
  minutes_down: number;
}

export interface Allocation {
  id: number;
  pool: string;
  resource: string;
  ip: string | null;
  prefix: string | null;
  int_value: number | null;
  status: "RESERVED" | "ALLOCATED" | "QUARANTINED" | "RELEASED";
  reserved_at: string;
  allocated_at: string | null;
  quarantine_until: string | null;
  released_at: string | null;
}

export interface Job {
  id: string;
  type: "PROVISION" | "DECOMMISSION" | "FORGET";
  status: JobStatus;
  attempt: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_summary: string | null;
  parent_job_id: string | null;
  site_id: string;
  site_code: string;
  site_name: string;
  site_number: number;
  requested_by_username: string;
}

export interface Step { step: string; label: string; status: string; changed: boolean; tasks: number }

export interface ZabbixHost {
  hostid: string;
  host: string;
  name: string;
  enabled: boolean;
  ip: string | null;
  snmp: "AVAILABLE" | "UNAVAILABLE" | "UNKNOWN" | "NONE";
  snmp_error: string | null;
  problems: { name: string; severity: number; clock: number }[];
}

export interface Me {
  id: string;
  username: string;
  full_name: string;
  roles: string[];
  permissions: string[];
}
