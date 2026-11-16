/** Export estático: Caddy sirve los archivos; no hace falta Node.js en la EC2. */
const nextConfig = {
  output: "export",
  basePath: "/portal_heladeria",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};
export default nextConfig;
