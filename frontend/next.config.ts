import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return {
      // NextAuth routes (/api/auth/*) are NOT rewritten — handled by Next.js
      beforeFiles: [],
      afterFiles: [
        {
          source: "/api/auth/:path(login|register|me)",
          destination: "http://localhost:8000/api/auth/:path",
        },
        {
          source: "/api/:path((?!auth).*)",
          destination: "http://localhost:8000/api/:path*",
        },
      ],
      fallback: [],
    };
  },
};

export default nextConfig;
