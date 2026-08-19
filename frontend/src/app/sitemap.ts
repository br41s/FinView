import fs from "node:fs";
import path from "node:path";

import type { MetadataRoute } from "next";

import { SITE_URL } from "@/lib/site";

/**
 * Blog slugs are read from the filesystem rather than a hand-maintained list, so
 * a new article appears in the sitemap by existing. A directory only counts as a
 * post once it has a page.mdx — a slug with styling but no content is not a page.
 *
 * This runs at build time (the blog routes are statically prerendered), so the
 * read costs nothing at request time.
 */
function blogSlugs(): string[] {
  const blogDir = path.join(process.cwd(), "src", "app", "blog");
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(blogDir, { withFileTypes: true });
  } catch {
    return [];
  }
  return entries
    .filter(
      (entry) =>
        entry.isDirectory() &&
        fs.existsSync(path.join(blogDir, entry.name, "page.mdx")),
    )
    .map((entry) => entry.name)
    .sort();
}

export default function sitemap(): MetadataRoute.Sitemap {
  const staticRoutes: MetadataRoute.Sitemap = [
    { url: `${SITE_URL}/`, priority: 1 },
    { url: `${SITE_URL}/blog`, priority: 0.8 },
    { url: `${SITE_URL}/features`, priority: 0.6 },
    { url: `${SITE_URL}/pricing`, priority: 0.6 },
  ];

  const posts: MetadataRoute.Sitemap = blogSlugs().map((slug) => ({
    url: `${SITE_URL}/blog/${slug}`,
    priority: 0.7,
  }));

  return [...staticRoutes, ...posts];
}
