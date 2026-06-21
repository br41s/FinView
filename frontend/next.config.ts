import type { NextConfig } from "next";
import createMDX from '@next/mdx';

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

// Security headers applied to every response. Kept to non-breaking controls:
// a full content-CSP is intentionally omitted to avoid breaking Next.js inline
// scripts / Recharts; `frame-ancestors 'none'` is the real clickjacking control
// and supersedes X-Frame-Options on modern browsers (both sent for coverage).
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  pageExtensions: ['js', 'jsx', 'ts', 'tsx', 'md', 'mdx'],
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
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

const withMDX = createMDX({
  options: {
    remarkPlugins: [['remark-gfm']],
  },
});
export default withMDX(nextConfig);
