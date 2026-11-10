import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored shadcn/ui + ElevenLabs UI registry sources are kept verbatim for upgradability.
    "components/ui/**",
    "types/**",
    "public/worklets/**",
    "playwright-report/**",
    "test-results/**",
  ]),
  {
    rules: {
      // Fetch-then-setState inside effects is intentional in this app; the compiler rule flags async helpers too.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
