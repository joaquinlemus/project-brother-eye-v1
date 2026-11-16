"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";
import type { ApiError } from "@/lib/api";
import { C } from "@/lib/theme";

export function PageHeader({ title, subtitle, actions, back }:
  { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode; back?: ReactNode }) {
  return (
    <Box sx={{ mb: 3 }}>
      {back}
      <Box sx={{ display: "flex", gap: 2, alignItems: { sm: "flex-end" }, justifyContent: "space-between",
        flexDirection: { xs: "column", sm: "row" } }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="h1">{title}</Typography>
          {subtitle && <Typography color="text.secondary" sx={{ mt: 0.75, maxWidth: "70ch" }}>{subtitle}</Typography>}
        </Box>
        {actions && <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>{actions}</Box>}
      </Box>
    </Box>
  );
}

export function Section({ title, aside, children, pad = true }:
  { title: string; aside?: ReactNode; children: ReactNode; pad?: boolean }) {
  return (
    <Box component="section" sx={{ mb: 4 }}>
      <Box sx={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 2, mb: 1.25 }}>
        <Typography variant="h2" component="h2">{title}</Typography>
        {aside}
      </Box>
      <Box sx={{ border: `1px solid ${C.line}`, borderRadius: 1.5, background: C.paper, overflow: "hidden",
        ...(pad && { p: { xs: 2, sm: 2.5 } }) }}>
        {children}
      </Box>
    </Box>
  );
}

export function Loading({ label = "Cargando…" }: { label?: string }) {
  return (
    <Box role="status" sx={{ display: "flex", alignItems: "center", gap: 1.5, p: 3, color: "text.secondary" }}>
      <CircularProgress size={18} thickness={5} /> {label}
    </Box>
  );
}

export function LoadError({ error, retry }: { error: ApiError; retry?: () => void }) {
  return (
    <Alert severity="error" sx={{ m: 2 }}
      action={retry && <Button color="inherit" size="small" onClick={retry}>Reintentar</Button>}>
      {error.message}
    </Alert>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <Box sx={{ p: { xs: 3, sm: 5 }, textAlign: "center" }}>
      <Typography variant="h3" sx={{ mb: 0.75 }}>{title}</Typography>
      {children && <Typography color="text.secondary" sx={{ maxWidth: "52ch", mx: "auto" }}>{children}</Typography>}
      {action && <Box sx={{ mt: 2 }}>{action}</Box>}
    </Box>
  );
}

export function Mono({ children }: { children: ReactNode }) {
  return <Box component="span" sx={{ fontFamily: '"IBM Plex Mono", monospace', fontSize: 13 }}>{children}</Box>;
}
