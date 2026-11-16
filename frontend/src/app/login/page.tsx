"use client";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";
import { useState, type FormEvent } from "react";
import { api, ApiError, BASE_PATH } from "@/lib/api";
import { C, mono } from "@/lib/theme";

type LoginResp =
  | { status: "MFA_REQUIRED"; mfa_token: string }
  | { status: "MFA_SETUP_REQUIRED"; mfa_token: string; otpauth_uri: string; secret: string; qr_svg: string };

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<LoginResp | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submitPassword = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      setStep(await api.post<LoginResp>("/auth/login", { username, password }));
      setPassword("");
    } catch (err) {
      setError((err as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  const submitCode = async (e: FormEvent) => {
    e.preventDefault();
    if (!step) return;
    setBusy(true);
    setError(null);
    try {
      await api.post("/auth/mfa", { mfa_token: step.mfa_token, code });
      window.location.href = `${BASE_PATH}/`;
    } catch (err) {
      const ae = err as ApiError;
      setError(ae.message);
      if (ae.message.includes("expiró")) setStep(null);
      setCode("");
      setBusy(false);
    }
  };

  return (
    <Box sx={{ minHeight: "100vh", display: "grid", gridTemplateColumns: { md: "minmax(320px, 5fr) 7fr" },
      gridTemplateRows: { xs: "auto 1fr", md: "none" } }}>
      <Box sx={{ background: C.ink, color: "#fff", p: { xs: 3, md: 6 }, display: "flex", flexDirection: "column",
        justifyContent: { md: "space-between" }, gap: 3 }}>
        <Box component="img" src={`${BASE_PATH}/logo-completo.webp`}
          alt="Heladería Leche de Cabra, SDN y orquestación"
          sx={{ display: "block", width: { xs: 190, md: "min(100%, 400px)" }, height: "auto", mx: { xs: "auto", md: 0 } }} />
        <Box sx={{ display: { xs: "none", md: "block" } }}>
          <Typography sx={{ fontFamily: '"Bricolage Grotesque Variable"', fontSize: 40, fontWeight: 700,
            lineHeight: 1.05, letterSpacing: "-0.02em", maxWidth: "12ch" }}>
            Cada sucursal, conectada sin tocar un router.
          </Typography>
          <Typography sx={{ color: "#B8C4D0", mt: 2, maxWidth: "44ch" }}>
            Abre y cierra sucursales en la red DMVPN de dos hubs. Ansible configura el router y
            Zabbix empieza a monitorearlo.
          </Typography>
        </Box>
        <Typography sx={{ color: "#8496A8", fontSize: 13, display: { xs: "none", md: "block" } }}>
          Acceso restringido. Toda la actividad queda registrada.
        </Typography>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", justifyContent: "center", p: { xs: 3, sm: 6 } }}>
        <Box sx={{ width: "100%", maxWidth: 380 }}>
          {!step ? (
            <Box component="form" onSubmit={submitPassword} noValidate>
              <Typography variant="h1" sx={{ mb: 1 }}>Iniciar sesión</Typography>
              <Typography color="text.secondary" sx={{ mb: 3 }}>
                Después de tu contraseña te pediremos el código de tu aplicación de autenticación.
              </Typography>
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              <TextField label="Usuario" value={username} autoFocus autoComplete="username" required
                onChange={(e) => setUsername(e.target.value)} sx={{ mb: 2 }} />
              <TextField label="Contraseña" type="password" value={password} autoComplete="current-password"
                required onChange={(e) => setPassword(e.target.value)} sx={{ mb: 3 }} />
              <Button type="submit" variant="contained" size="large" fullWidth
                disabled={busy || !username || !password}>
                {busy ? "Verificando…" : "Continuar"}
              </Button>
            </Box>
          ) : (
            <Box component="form" onSubmit={submitCode} noValidate>
              <Typography variant="h1" sx={{ mb: 1 }}>
                {step.status === "MFA_SETUP_REQUIRED" ? "Activa tu segundo factor" : "Código de verificación"}
              </Typography>
              {step.status === "MFA_SETUP_REQUIRED" ? (
                <>
                  <Typography color="text.secondary" sx={{ mb: 2 }}>
                    Escanea el código con Google Authenticator, Microsoft Authenticator o similar, y escribe
                    los 6 dígitos que aparecen. Solo se hace una vez.
                  </Typography>
                  <Box sx={{ display: "flex", justifyContent: "center", mb: 1.5, "& svg": { width: 200, height: 200 } }}
                    dangerouslySetInnerHTML={{ __html: step.qr_svg }} />
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 2, textAlign: "center" }}>
                    ¿No puedes escanear? Clave manual:{" "}
                    <Box component="span" sx={{ fontFamily: mono, color: C.ink, wordBreak: "break-all" }}>
                      {step.secret}
                    </Box>
                  </Typography>
                </>
              ) : (
                <Typography color="text.secondary" sx={{ mb: 3 }}>
                  Abre tu aplicación de autenticación y escribe el código de 6 dígitos de este portal.
                </Typography>
              )}
              {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
              <TextField label="Código de 6 dígitos" value={code} autoFocus autoComplete="one-time-code"
                inputMode="numeric" onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                slotProps={{ htmlInput: { style: { fontFamily: mono, fontSize: 22, letterSpacing: "0.3em" } } }}
                sx={{ mb: 3 }} />
              <Button type="submit" variant="contained" size="large" fullWidth disabled={busy || code.length !== 6}>
                {busy ? "Verificando…" : "Entrar al portal"}
              </Button>
              <Button fullWidth sx={{ mt: 1 }} onClick={() => { setStep(null); setError(null); setCode(""); }}>
                Usar otro usuario
              </Button>
            </Box>
          )}
        </Box>
      </Box>
    </Box>
  );
}
