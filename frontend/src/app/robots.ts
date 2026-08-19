import type { MetadataRoute } from "next";

import { PRIVATE_ROUTES, SITE_URL } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // Everything behind a session. These pages render nothing useful to a
      // crawler and should not compete with the articles in the index.
      disallow: PRIVATE_ROUTES.map((route) => `${route}/`),
    },
    sitemap: `${SITE_URL}/sitemap.xml`,
    host: SITE_URL,
  };
}
