import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    tsconfigPaths: true,
  },
  // Tests import modules that pull in CSS modules (the blog index reaches
  // blog.module.css through its illustrations). Vite would hand those to the
  // project's PostCSS config, and Tailwind 4's plugin is not loadable that way.
  // Tests never assert on styling, so an empty plugin list short-circuits it.
  css: {
    postcss: { plugins: [] },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
