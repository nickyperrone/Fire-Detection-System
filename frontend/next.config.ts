import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

// Every response (docs/04-frontend.md#security-headers). The policy is narrow on purpose: no other
// site can frame the app or receive a form from it; map tiles, fonts and Cloudflare's check load
// as before.
const SECURITY_HEADERS = [
  {
    key: "Content-Security-Policy",
    value:
      "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'",
  },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Permissions-Policy",
    value: "geolocation=(self), camera=(), microphone=(), payment=()",
  },
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
];

const nextConfig: NextConfig = {
  // A server with only the files it needs, for the Docker image (docs/14-deploy.md).
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  // The browser only talks to this origin; Next.js forwards /api to FastAPI (no CORS setup).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
