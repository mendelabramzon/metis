/* eslint-env node */
module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended-type-checked",
    "plugin:react-hooks/recommended",
    "plugin:jsx-a11y/recommended",
  ],
  parser: "@typescript-eslint/parser",
  parserOptions: {
    project: ["./tsconfig.json"],
    tsconfigRootDir: __dirname,
    ecmaVersion: "latest",
    sourceType: "module",
  },
  plugins: ["@typescript-eslint", "react-refresh", "jsx-a11y"],
  settings: { react: { version: "18.3" } },
  ignorePatterns: ["dist", "node_modules", ".eslintrc.cjs"],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    // Status colors and tokens come from CSS variables; inline styles are allowed where layout
    // is component-local. No app-specific overrides needed beyond the recommended sets yet.
  },
};
