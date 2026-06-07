import type { NextConfig } from "next";
import createMDX from '@next/mdx';
import remarkGfm from 'remark-gfm';

const backendUrl = process.env.BACKEND_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  pageExtensions: ['js', 'jsx', 'ts', 'tsx', 'md', 'mdx'],
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
    remarkPlugins: [remarkGfm],
  },
});
export default withMDX(nextConfig);
