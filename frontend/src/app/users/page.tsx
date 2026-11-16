"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import FormControlLabel from "@mui/material/FormControlLabel";
import FormGroup from "@mui/material/FormGroup";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState } from "react";
import AppShell from "@/components/AppShell";
import { LoadError, Loading, PageHeader, Section } from "@/components/Page";
import { api, ApiError } from "@/lib/api";
import { ago, ROLE } from "@/lib/format";
import { C } from "@/lib/theme";
import { useApi } from "@/lib/useApi";

interface User {
  id: string; username: string; email: string; full_name: string; is_active: boolean; mfa_enabled: boolean;
  last_login_at: string | null; locked_until: string | null; roles: string[];
}
type Dlg = { kind: "create" } | { kind: "roles"; u: User } | { kind: "password"; u: User } | null;

function RolePicker({ value, onChange }: { value: string[]; onChange: (v: string[]) => void }) {
  return (
    <FormGroup>
      {Object.entries(ROLE).map(([k, l]) => (
        <FormControlLabel key={k} label={l} control={
          <Checkbox checked={value.includes(k)}
            onChange={(e) => onChange(e.target.checked ? [...value, k] : value.filter((r) => r !== k))} />} />
      ))}
    </FormGroup>
  );
}

function UserDialog({ dlg, onClose, onDone }: { dlg: NonNullable<Dlg>; onClose: () => void; onDone: (m: string) => void }) {
  const [f, setF] = useState({ username: "", email: "", full_name: "", password: "",
    roles: dlg.kind === "roles" ? dlg.u.roles : ["viewer"] });
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (dlg.kind === "create") {
        await api.post("/users", f);
        onDone(`Usuario ${f.username} creado. En su primer ingreso escaneará el QR de MFA.`);
      } else if (dlg.kind === "roles") {
        await api.patch(`/users/${dlg.u.id}`, { roles: f.roles });
        onDone(`Roles de ${dlg.u.username} actualizados.`);
      } else {
        await api.post(`/users/${dlg.u.id}/password`, { password: f.password });
        onDone(`Contraseña temporal asignada a ${dlg.u.username}; la cuenta quedó desbloqueada.`);
      }
    } catch (e) {
      const ae = e as ApiError;
      setErr(ae.fields?.map((x) => `${x.field}: ${x.message}`).join(". ") || ae.message);
      setBusy(false);
    }
  };
  const title = dlg.kind === "create" ? "Crear usuario" : dlg.kind === "roles" ? `Roles de ${dlg.u.username}`
    : `Contraseña temporal para ${dlg.u.username}`;
  return (
    <Dialog open onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ fontFamily: '"Bricolage Grotesque Variable"', fontWeight: 700 }}>{title}</DialogTitle>
      <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, pt: "8px !important" }}>
        {err && <Alert severity="error">{err}</Alert>}
        {dlg.kind === "create" && <>
          <TextField label="Usuario" value={f.username} helperText="Minúsculas, números, punto o guion"
            onChange={(e) => setF({ ...f, username: e.target.value.toLowerCase() })} />
          <TextField label="Nombre completo" value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} />
          <TextField label="Correo" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />
        </>}
        {dlg.kind !== "roles" && (
          <TextField label={dlg.kind === "create" ? "Contraseña inicial" : "Contraseña temporal"} type="password"
            value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })}
            helperText="Mínimo 10 caracteres, con letras y números o símbolos" />)}
        {dlg.kind !== "password" && <Box><Typography variant="body2" color="text.secondary">Roles</Typography>
          <RolePicker value={f.roles} onChange={(roles) => setF({ ...f, roles })} /></Box>}
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2.5 }}>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" onClick={save} disabled={busy || (dlg.kind !== "password" && f.roles.length === 0)}>
          {dlg.kind === "create" ? "Crear usuario" : dlg.kind === "roles" ? "Guardar roles" : "Asignar contraseña"}
        </Button>
      </DialogActions>
    </Dialog>
  );
}

function Users() {
  const { data, error, reload } = useApi<User[]>("/users");
  const [dlg, setDlg] = useState<Dlg>(null);
  const [menu, setMenu] = useState<{ el: HTMLElement; u: User } | null>(null);
  const [msg, setMsg] = useState<{ sev: "success" | "error"; text: string } | null>(null);
  if (error) return <LoadError error={error} retry={reload} />;
  if (!data) return <Loading />;
  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setMenu(null);
    try { await fn(); setMsg({ sev: "success", text: ok }); reload(); }
    catch (e) { setMsg({ sev: "error", text: (e as ApiError).message }); }
  };
  return (
    <>
      <PageHeader title="Usuarios"
        subtitle="Todos los usuarios usan contraseña y un código de su aplicación de autenticación."
        actions={<Button variant="contained" onClick={() => setDlg({ kind: "create" })}>Crear usuario</Button>} />
      {msg && <Alert severity={msg.sev} onClose={() => setMsg(null)} sx={{ mb: 2 }}>{msg.text}</Alert>}
      <Section title="Cuentas" pad={false}>
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Usuario</TableCell><TableCell>Roles</TableCell><TableCell>MFA</TableCell>
              <TableCell>Estado</TableCell><TableCell>Último ingreso</TableCell><TableCell />
            </TableRow></TableHead>
            <TableBody>
              {data.map((u) => {
                const locked = u.locked_until && new Date(u.locked_until) > new Date();
                return (
                  <TableRow key={u.id}>
                    <TableCell>
                      <Typography sx={{ fontWeight: 600, fontSize: 14 }}>{u.full_name}</Typography>
                      <Typography variant="body2" color="text.secondary">{u.username}, {u.email}</Typography>
                    </TableCell>
                    <TableCell>{u.roles.map((r) => ROLE[r] ?? r).join(", ") || "Sin rol"}</TableCell>
                    <TableCell>{u.mfa_enabled ? "Activo" : "Pendiente de activar"}</TableCell>
                    <TableCell sx={{ color: !u.is_active || locked ? C.fresa : C.ink }}>
                      {!u.is_active ? "Desactivado" : locked ? "Bloqueado por intentos" : "Activo"}
                    </TableCell>
                    <TableCell>{u.last_login_at ? ago(u.last_login_at) : "Nunca"}</TableCell>
                    <TableCell align="right">
                      <Button size="small" onClick={(e) => setMenu({ el: e.currentTarget, u })}
                        aria-haspopup="menu">Gestionar</Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </Section>
      <Menu anchorEl={menu?.el} open={!!menu} onClose={() => setMenu(null)}>
        {menu && [
          <MenuItem key="r" onClick={() => { setDlg({ kind: "roles", u: menu.u }); setMenu(null); }}>Cambiar roles</MenuItem>,
          <MenuItem key="p" onClick={() => { setDlg({ kind: "password", u: menu.u }); setMenu(null); }}>
            Asignar contraseña temporal</MenuItem>,
          <MenuItem key="m" onClick={() => act(() => api.post(`/users/${menu.u.id}/reset-mfa`),
            `MFA de ${menu.u.username} reiniciado: escaneará un QR nuevo al ingresar.`)}>Reiniciar MFA</MenuItem>,
          <MenuItem key="a" onClick={() => act(() => api.patch(`/users/${menu.u.id}`, { is_active: !menu.u.is_active }),
            `${menu.u.username} ${menu.u.is_active ? "desactivado" : "activado"}.`)}>
            {menu.u.is_active ? "Desactivar" : "Activar"}</MenuItem>,
        ]}
      </Menu>
      {dlg && <UserDialog dlg={dlg} onClose={() => setDlg(null)}
        onDone={(text) => { setDlg(null); setMsg({ sev: "success", text }); reload(); }} />}
    </>
  );
}

export default function Page() {
  return <AppShell><Users /></AppShell>;
}
