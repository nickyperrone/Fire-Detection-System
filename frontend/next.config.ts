import type { NextConfig } from "next";

const apiUrl = process.env.API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The browser only talks to this origin; Next.js forwards /api to FastAPI (no CORS setup).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
