"use client";
import Box from "@mui/material/Box";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Link from "next/link";
import type { Job } from "@/lib/api";
import { ago, fmtDuration, JOB_TYPE } from "@/lib/format";
import { C } from "@/lib/theme";
import { JobStatusChip } from "./Status";

export default function JobsTable({ jobs, showSite = true }: { jobs: Job[]; showSite?: boolean }) {
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>Trabajo</TableCell>
            {showSite && <TableCell>Sucursal</TableCell>}
            <TableCell>Estado</TableCell>
            <TableCell>Duración</TableCell>
            <TableCell>Solicitado por</TableCell>
            <TableCell>Cuándo</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {jobs.map((j) => (
            <TableRow key={j.id} hover>
              <TableCell>
                <Box component={Link} href={`/jobs/detail/?id=${j.id}`}
                  sx={{ color: C.mora, fontWeight: 600, textDecoration: "none", "&:hover": { textDecoration: "underline" } }}>
                  {JOB_TYPE[j.type] ?? j.type} de R{j.site_number}
                </Box>
                {j.attempt > 1 && <Box component="span" sx={{ color: "text.secondary", ml: 1 }}>intento {j.attempt}</Box>}
              </TableCell>
              {showSite && <TableCell>{j.site_name}</TableCell>}
              <TableCell><JobStatusChip status={j.status} /></TableCell>
              <TableCell>{fmtDuration(j.started_at, j.finished_at)}</TableCell>
              <TableCell>{j.requested_by_username}</TableCell>
              <TableCell sx={{ whiteSpace: "nowrap" }}>{ago(j.created_at)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
}
