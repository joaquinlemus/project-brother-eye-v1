import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ padding: 48, fontFamily: "IBM Plex Sans, sans-serif" }}>
      <h1>Esta página no existe</h1>
      <p><Link href="/">Volver al inicio del portal</Link></p>
    </main>
  );
}
