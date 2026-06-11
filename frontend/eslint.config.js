import js from "@eslint/js";
import globals from "globals";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Build output and the bundled SPA copy aren't linted.
  { ignores: ["dist", "../src/gpxsheet/service/static", "playwright-report", "test-results"] },
  {
    files: ["**/*.{ts,tsx}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2021,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // We keep rules-of-hooks and exhaustive-deps (they catch real bugs), but turn
      // off the v6 set-state-in-effect rule: every hit here is an idiomatic pattern
      // (object-URL create/cleanup, reset-on-prop-change, job-status sync), not a bug.
      "react-hooks/set-state-in-effect": "off",
      "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    },
  },
  // Playwright specs run under Node and use the test globals.
  {
    files: ["tests/**/*.ts"],
    languageOptions: { globals: { ...globals.node } },
  },
);
