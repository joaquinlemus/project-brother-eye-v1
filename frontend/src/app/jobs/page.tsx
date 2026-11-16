"use client";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import JobsTable from "@/components/JobsTable";
import { Empty, LoadError, Loading, PageHeader, Section } from "@/components/Page";
import type { Job } from "@/lib/api";
import { useApi } from "@/lib/useApi";

const TABS = [["", "Todos"], ["RUNNING", "Ejecutando"], ["QUEUED", "En cola"], ["FAILED", "Fallidos"],
  ["SUCCEEDED", "Completados"]] as const;

function Jobs() {
  const [st, setSt] = useState("");
  const { data, error, reload } = useApi<Job[]>(`/jobs?limit=100${st ? `&status=${st}` : ""}`, 5000);
  return (
    <>
      <PageHeader title="Trabajos de Ansible"
        subtitle="Cada alta o baja es un trabajo. Se ejecutan en orden, uno a la vez, porque todos tocan los dos hubs." />
      <Tabs value={st} onChange={(_, v) => setSt(v)} variant="scrollable" sx={{ mb: 1.5 }}>
        {TABS.map(([k, l]) => <Tab key={k} value={k} label={l} />)}
      </Tabs>
      <Section title={TABS.find(([k]) => k === st)![1]} pad={false}>
        {error ? <LoadError error={error} retry={reload} /> : !data ? <Loading /> : data.length ? (
          <JobsTable jobs={data} />
        ) : <Empty title="No hay trabajos en esta vista" />}
      </Section>
    </>
  );
}

export default function Page() {
  return <AppShell><Jobs /></AppShell>;
}
