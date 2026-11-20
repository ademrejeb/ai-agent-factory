import path from "node:path";

import type { NextConfig } from "next";

// The browser always talks to the same origin. Next proxies control-plane
// requests to FastAPI, which keeps session cookies first-party and avoids
// exposing the API host to client bundles.
const API_ORIGIN = process.env.API_ORIGIN ?? "http://localhost:8080";

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  experimental: {
    // Next's rewrite proxy defaults to 30s. Local models and long provider runs
    // routinely exceed that, and SSE connections stay open while streaming.
    proxyTimeout: 300_000,
  },
  // Without an explicit root, Turbopack walks up to the user home directory
  // when it finds an unrelated lockfile, which broadens module resolution.
  turbopack: { root: path.resolve(process.cwd()) },
  async rewrites() {
    return [
      {
        source: "/backend-api/:path*",
        destination: `${API_ORIGIN}/:path*`,
      },
    ];
  },
};

export default nextConfig;
