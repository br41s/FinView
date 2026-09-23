import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  {
    // React Compiler rules introduced with eslint-plugin-react-hooks 6. They
    // flag 42 pre-existing sites (setState inside effects, components defined
    // during render) that each need a real decision, not a mechanical edit.
    // Warnings keep them visible without making `pnpm lint` red on debt that
    // predates the linter. Promote back to "error" as files are cleaned up.
    rules: {
      "react-hooks/set-state-in-effect": "warn",
      "react-hooks/static-components": "warn",
    },
  },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
