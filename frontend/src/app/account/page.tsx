"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import { useState, type FormEvent } from "react";
import AppShell from "@/components/AppShell";
import { PageHeader } from "@/components/Page";
import { api, ApiError } from "@/lib/api";

function Account() {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [rep, setRep] = useState("");
  const [msg, setMsg] = useState<{ sev: "success" | "error"; text: string } | null>(null);
  const mismatch = rep.length > 0 && rep !== next;
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await api.post("/auth/password", { current_password: cur, new_password: next });
      setMsg({ sev: "success", text: "Contraseña cambiada." });
      setCur(""); setNext(""); setRep("");
    } catch (err) {
      setMsg({ sev: "error", text: (err as ApiError).message });
    }
  };
  return (
    <>
      <PageHeader title="Cambiar contraseña" subtitle="Usa al menos 10 caracteres, con letras y números o símbolos." />
      <Box component="form" onSubmit={submit} sx={{ maxWidth: 380, display: "flex", flexDirection: "column", gap: 2 }}>
        {msg && <Alert severity={msg.sev}>{msg.text}</Alert>}
        <TextField label="Contraseña actual" type="password" autoComplete="current-password" value={cur}
          onChange={(e) => setCur(e.target.value)} />
        <TextField label="Contraseña nueva" type="password" autoComplete="new-password" value={next}
          onChange={(e) => setNext(e.target.value)} />
        <TextField label="Repite la contraseña nueva" type="password" autoComplete="new-password" value={rep}
          onChange={(e) => setRep(e.target.value)} error={mismatch}
          helperText={mismatch ? "No coincide con la contraseña nueva" : " "} />
        <Box><Button type="submit" variant="contained" disabled={!cur || next.length < 10 || next !== rep}>
          Cambiar contraseña</Button></Box>
      </Box>
    </>
  );
}

export default function Page() {
  return <AppShell><Account /></AppShell>;
}
