"use client";
import AccountTreeOutlined from "@mui/icons-material/AccountTreeOutlined";
import FactCheckOutlined from "@mui/icons-material/FactCheckOutlined";
import HubOutlined from "@mui/icons-material/HubOutlined";
import LogoutOutlined from "@mui/icons-material/LogoutOutlined";
import ManageAccountsOutlined from "@mui/icons-material/ManageAccountsOutlined";
import MenuIcon from "@mui/icons-material/Menu";
import MonitorHeartOutlined from "@mui/icons-material/MonitorHeartOutlined";
import PasswordOutlined from "@mui/icons-material/PasswordOutlined";
import PlaylistPlayOutlined from "@mui/icons-material/PlaylistPlayOutlined";
import StorefrontOutlined from "@mui/icons-material/StorefrontOutlined";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Typography from "@mui/material/Typography";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { api, BASE_PATH, type Me } from "@/lib/api";
import { ROLE } from "@/lib/format";
import { C } from "@/lib/theme";
import OfflinePrompt from "./OfflinePrompt";
import { Loading } from "./Page";

const MeContext = createContext<Me | null>(null);
export const useMe = () => useContext(MeContext)!;
export const can = (me: Me | null, perm: string) => !!me?.permissions.includes(perm);

const NAV = [
  { href: "/", label: "Inicio", icon: HubOutlined, perm: "site:read" },
  { href: "/sites/", label: "Sucursales", icon: StorefrontOutlined, perm: "site:read" },
  { href: "/jobs/", label: "Trabajos de Ansible", icon: PlaylistPlayOutlined, perm: "job:read" },
  { href: "/ipam/", label: "IPAM", icon: AccountTreeOutlined, perm: "ipam:read" },
  { href: "/monitoring/", label: "Monitoreo", icon: MonitorHeartOutlined, perm: "site:read" },
  { href: "/audit/", label: "Auditoría", icon: FactCheckOutlined, perm: "audit:read" },
  { href: "/users/", label: "Usuarios", icon: ManageAccountsOutlined, perm: "user:admin" },
];

export function BrandMark({ size = 30 }: { size?: number }) {
  // Emblema circular del logo (la versión completa, con texto, va en el inicio de sesión)
  return (
    <Box component="img" src={`${BASE_PATH}/logo-emblema.png`} alt="" width={size} height={size}
      sx={{ display: "block", flexShrink: 0, borderRadius: "50%" }} />
  );
}

function Nav({ me, onNavigate }: { me: Me; onNavigate?: () => void }) {
  const path = usePathname() || "/";
  const active = (href: string) => (href === "/" ? path === "/" : path.startsWith(href.replace(/\/$/, "")));
  const logout = async () => {
    await api.post("/auth/logout").catch(() => undefined);
    window.location.href = `${BASE_PATH}/login/`;
  };
  const item = {
    display: "flex", alignItems: "center", gap: 1.5, px: 1.5, py: 1, borderRadius: 1,
    color: "#C9D2DB", textDecoration: "none", fontSize: 14, fontWeight: 500,
    "&:hover": { background: "#26374A", color: "#fff" },
  } as const;
  return (
    <Box sx={{ display: "flex", flexDirection: "column", height: "100%", p: 2, gap: 0.5 }}>
      <Box component={Link} href="/" onClick={onNavigate}
        sx={{ display: "flex", alignItems: "center", gap: 1.25, px: 1, pb: 2.5, pt: 0.5, color: "#fff",
          textDecoration: "none" }}>
        <BrandMark size={44} />
        <Box>
          <Typography sx={{ fontFamily: '"Bricolage Grotesque Variable"', fontWeight: 700, fontSize: 17,
            lineHeight: 1.1 }}>Leche de Cabra</Typography>
          <Typography sx={{ fontSize: 12, color: "#9FB0C0" }}>Red de sucursales</Typography>
        </Box>
      </Box>
      <Box component="nav" aria-label="Secciones" sx={{ display: "flex", flexDirection: "column", gap: 0.25 }}>
        {NAV.filter((n) => can(me, n.perm)).map(({ href, label, icon: Icon }) => (
          <Box key={href} component={Link} href={href} onClick={onNavigate}
            aria-current={active(href) ? "page" : undefined}
            sx={{ ...item, ...(active(href) && { background: "#2C3F54", color: "#fff",
              boxShadow: `inset 3px 0 0 ${C.barquillo}` }) }}>
            <Icon sx={{ fontSize: 20 }} /> {label}
          </Box>
        ))}
      </Box>
      <Box sx={{ mt: "auto", pt: 2, borderTop: "1px solid #2C3F54" }}>
        <Box sx={{ px: 1.5, pb: 1.25 }}>
          <Typography sx={{ color: "#fff", fontWeight: 600, fontSize: 14 }}>{me.full_name}</Typography>
          <Typography sx={{ color: "#9FB0C0", fontSize: 12 }}>{me.username}</Typography>
          <Typography sx={{ color: "#9FB0C0", fontSize: 12 }}>
            {me.roles.map((r) => ROLE[r] ?? r).join(", ")}
          </Typography>
        </Box>
        <Box component={Link} href="/account/" onClick={onNavigate} sx={item}>
          <PasswordOutlined sx={{ fontSize: 20 }} /> Cambiar contraseña
        </Box>
        <Box component="button" onClick={logout}
          sx={{ ...item, width: "100%", border: 0, background: "none", cursor: "pointer", fontFamily: "inherit" }}>
          <LogoutOutlined sx={{ fontSize: 20 }} /> Cerrar sesión
        </Box>
      </Box>
    </Box>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api.get<Me>("/auth/me").then(setMe).catch(() => {
      window.location.href = `${BASE_PATH}/login/`;
    });
  }, []);
  if (!me) return <Loading label="Verificando sesión…" />;
  return (
    <MeContext.Provider value={me}>
      <Box sx={{ display: "flex", minHeight: "100vh" }}>
        <Box component="aside" sx={{ display: { xs: "none", md: "block" }, width: 248, flexShrink: 0,
          background: C.ink, position: "sticky", top: 0, height: "100vh" }}>
          <Nav me={me} />
        </Box>
        <Drawer open={open} onClose={() => setOpen(false)}
          slotProps={{ paper: { sx: { width: 264, background: C.ink, border: 0 } } }}>
          <Nav me={me} onNavigate={() => setOpen(false)} />
        </Drawer>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Box sx={{ display: { xs: "flex", md: "none" }, alignItems: "center", gap: 1, px: 1.5, py: 1,
            background: C.ink, color: "#fff", position: "sticky", top: 0, zIndex: 10 }}>
            <IconButton aria-label="Abrir menú" onClick={() => setOpen(true)} sx={{ color: "#fff" }}>
              <MenuIcon />
            </IconButton>
            <BrandMark size={28} />
            <Typography sx={{ fontWeight: 700 }}>Leche de Cabra</Typography>
          </Box>
          <Box component="main" sx={{ px: { xs: 2, sm: 4 }, py: { xs: 3, sm: 4 }, maxWidth: 1240 }}>
            {children}
          </Box>
          {can(me, "site:forget") && <OfflinePrompt />}
        </Box>
      </Box>
    </MeContext.Provider>
  );
}
