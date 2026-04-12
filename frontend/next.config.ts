import type { NextConfig } from "next";

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return {
      // NextAuth routes (/api/auth/*) are NOT rewritten — handled by Next.js
      beforeFiles: [],
      afterFiles: [
        {
          source: "/api/auth/:path(login|register|me)",
          destination: `${backendUrl}/api/auth/:path`,
        },
        {
          source: "/api/:path((?!auth).*)",
          destination: `${backendUrl}/api/:path*`,
        },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
