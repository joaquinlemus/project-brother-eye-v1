"use client";
import { createTheme } from "@mui/material/styles";

// Paleta: "leche" fría de fondo, tinta pizarra, y los estados como sabores de helado.
export const C = {
  milk: "#FAFBFA",
  paper: "#FFFFFF",
  ink: "#1B2B3A",       // mismo fondo que el logo
  inkSoft: "#4A5866",
  line: "#DCE1E5",
  wash: "#F1F4F2",
  mora: "#6B3A6E",       // acción principal (zarzamora)
  pistacho: "#5E8C4A",   // activa / correcto
  barquillo: "#B7791F",  // en proceso
  fresa: "#C2414F",      // error
  vainilla: "#9AA3AD",   // retirada / inactiva
};

const display = '"Bricolage Grotesque Variable", "Segoe UI", sans-serif';
const body = '"IBM Plex Sans", "Segoe UI", system-ui, sans-serif';
export const mono = '"IBM Plex Mono", ui-monospace, monospace';

export const theme = createTheme({
  palette: {
    primary: { main: C.mora, contrastText: "#fff" },
    success: { main: C.pistacho },
    warning: { main: C.barquillo },
    error: { main: C.fresa },
    text: { primary: C.ink, secondary: C.inkSoft },
    background: { default: C.milk, paper: C.paper },
    divider: C.line,
  },
  shape: { borderRadius: 6 },
  typography: {
    fontFamily: body,
    fontSize: 14,
    h1: { fontFamily: display, fontWeight: 700, fontSize: "2rem", lineHeight: 1.15, letterSpacing: "-0.02em" },
    h2: { fontFamily: display, fontWeight: 650, fontSize: "1.375rem", lineHeight: 1.25, letterSpacing: "-0.01em" },
    h3: { fontFamily: display, fontWeight: 600, fontSize: "1.125rem", lineHeight: 1.3 },
    subtitle1: { fontWeight: 500 },
    body1: { lineHeight: 1.55 },
    body2: { lineHeight: 1.5 },
    button: { textTransform: "none", fontWeight: 600, letterSpacing: 0 },
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: {
      defaultProps: { elevation: 0 },
      styleOverrides: { root: { border: `1px solid ${C.line}` } },
    },
    MuiTableCell: {
      styleOverrides: {
        head: { fontWeight: 600, color: C.inkSoft, background: C.wash, whiteSpace: "nowrap" },
        root: { borderColor: C.line },
      },
    },
    MuiTooltip: { defaultProps: { arrow: true } },
    MuiTextField: { defaultProps: { size: "small", fullWidth: true } },
    MuiDialog: { styleOverrides: { paper: { border: "none" } } },
    MuiMenu: { styleOverrides: { paper: { border: `1px solid ${C.line}` } } },
    MuiCssBaseline: {
      styleOverrides: {
        body: { WebkitFontSmoothing: "antialiased" },
        ":focus-visible": { outline: `2px solid ${C.mora}`, outlineOffset: 2 },
        "@media (prefers-reduced-motion: reduce)": {
          "*": { animationDuration: "0.01ms !important", transitionDuration: "0.01ms !important" },
        },
      },
    },
  },
});
